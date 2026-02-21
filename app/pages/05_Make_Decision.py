import streamlit as st
import pandas as pd
from app.db.database import get_connection

def normalize_inverse(series: pd.Series) -> pd.Series:
    min_v = float(series.min())
    max_v = float(series.max())
    if max_v == min_v:
        return series.apply(lambda _: 100.0)
    return (max_v - series) / (max_v - min_v) * 100.0

def risk_penalty(risk: str) -> float:
    return {"Low": 0.0, "Medium": -15.0, "High": -40.0}.get(risk, -15.0)

def compute_cheapest_and_recommended(quotes: pd.DataFrame):
    # cheapest
    cheapest_row = quotes.sort_values("price", ascending=True).iloc[0]
    cheapest_vendor_id = int(cheapest_row["vendor_id"])

    # recommended (same scoring as dashboard)
    df_sc = quotes.copy()
    df_sc["price_score"] = normalize_inverse(df_sc["price"])
    df_sc["lt_score"] = normalize_inverse(df_sc["lead_time_days"])
    df_sc["risk_penalty"] = df_sc["risk_rating"].apply(risk_penalty)
    df_sc["final_score"] = 0.65 * df_sc["price_score"] + 0.35 * df_sc["lt_score"] + df_sc["risk_penalty"]

    rec_row = df_sc.sort_values("final_score", ascending=False).iloc[0]
    recommended_vendor_id = int(rec_row["vendor_id"])

    weights = "price=0.65,lead=0.35,penalty_high=-40,penalty_medium=-15,penalty_low=0"
    return cheapest_vendor_id, recommended_vendor_id, weights

def word_count(text: str) -> int:
    if not text:
        return 0
    # Count words robustly (split on whitespace)
    return len(text.strip().split())

def validate_override_reason(reason: str, min_words: int = 5, max_words: int = 50):
    wc = word_count(reason)
    if wc < min_words:
        return False, f"Please add proper reason in more than {min_words} words (max {max_words})."
    if wc > max_words:
        return False, f"Reason too long. Keep it within {max_words} words."
    return True, ""
    
st.set_page_config(page_title="Make Decision", layout="wide")
st.title("Make Decision (Purchase / Approver)")
st.caption("Select final vendor for an RFQ and log decision with audit trail.")

conn = get_connection()

# Get RFQs
rfq_df = pd.read_sql_query(
    """
    SELECT rfq.rfq_id, pr.pr_id, rm.rm_name, pr.qty, pr.need_by, pr.site
    FROM rfq
    JOIN pr ON rfq.pr_id = pr.pr_id
    JOIN rm_master rm ON pr.rm_id = rm.rm_id
    ORDER BY rfq.rfq_id DESC
    """,
    conn
)

if rfq_df.empty:
    st.warning("No RFQs found.")
    conn.close()
    st.stop()

rfq_options = rfq_df["rfq_id"].tolist()
selected_rfq = st.selectbox("Select RFQ", rfq_options)

rfq_info = rfq_df[rfq_df["rfq_id"] == selected_rfq].iloc[0]
st.info(
    f"**RFQ {selected_rfq}** | RM: **{rfq_info['rm_name']}** | Qty: **{rfq_info['qty']}** | Need-by: **{rfq_info['need_by']}** | Site: **{rfq_info['site']}**"
)

# Quotes for this RFQ
quotes_df = pd.read_sql_query(
    """
    SELECT q.quote_id, v.vendor_id, v.vendor_name, v.risk_rating, q.price, q.lead_time_days, q.payment_terms, q.validity_days, q.notes
    FROM quotes q
    JOIN vendors v ON q.vendor_id = v.vendor_id
    WHERE q.rfq_id = ?
    ORDER BY q.price ASC
    """,
    conn,
    params=(selected_rfq,)
)

st.subheader("Quotes")
st.dataframe(quotes_df, use_container_width=True)

cheapest_vendor_id, recommended_vendor_id, weights = compute_cheapest_and_recommended(quotes_df)

cheapest_name = quotes_df.loc[quotes_df["vendor_id"] == cheapest_vendor_id, "vendor_name"].iloc[0]
recommended_name = quotes_df.loc[quotes_df["vendor_id"] == recommended_vendor_id, "vendor_name"].iloc[0]

c1, c2 = st.columns(2)
c1.metric("System Cheapest", cheapest_name)
c2.metric("System Recommended", recommended_name)

# Decision form
st.subheader("Final Selection")
vendor_map = dict(zip(quotes_df["vendor_name"], quotes_df["vendor_id"]))
vendor_name = st.selectbox("Select Vendor", list(vendor_map.keys()))
selected_vendor_id = vendor_map[vendor_name]

selected_by = st.text_input("Selected by (name/role)", value="Purchase")
override_reason = st.text_area("Override reason (required if deviating from recommendation)", height=90)
st.caption(f"Reason word count: {word_count(override_reason)} (required: 5–50 if deviating)")

# Save decision
if st.button("Save Decision"):
    if not selected_by.strip():
        st.error("Selected by is required.")
    else:
        cheapest_vendor_id, recommended_vendor_id, weights = compute_cheapest_and_recommended(quotes_df)
        
        # Enforce override reason quality if deviating from recommendation
        if int(selected_vendor_id) != int(recommended_vendor_id):
            ok, msg = validate_override_reason(override_reason, min_words=5, max_words=50)
            if not ok:
                st.error(msg)
                st.stop()

        # Enforce override reason if deviating
        if selected_vendor_id != recommended_vendor_id and not override_reason.strip():
            st.error("Override reason is required because selected vendor differs from system recommendation.")
        else:
            cur = conn.cursor()

            # Save/Update snapshot
            cur.execute(
                """
                INSERT INTO rfq_recommendation_snapshot (rfq_id, recommended_vendor_id, cheapest_vendor_id, weights)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(rfq_id) DO UPDATE SET
                  recommended_vendor_id=excluded.recommended_vendor_id,
                  cheapest_vendor_id=excluded.cheapest_vendor_id,
                  weights=excluded.weights,
                  created_on=datetime('now')
                """,
                (int(selected_rfq), int(recommended_vendor_id), int(cheapest_vendor_id), weights)
            )

            # Save/Update decision
            cur.execute(
                """
                INSERT INTO rfq_decision (rfq_id, selected_vendor_id, selected_by, override_reason)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(rfq_id) DO UPDATE SET
                  selected_vendor_id=excluded.selected_vendor_id,
                  selected_by=excluded.selected_by,
                  override_reason=excluded.override_reason,
                  created_on=datetime('now')
                """,
                (
                    int(selected_rfq),
                    int(selected_vendor_id),
                    selected_by.strip(),
                    override_reason.strip() if override_reason else None
                )
            )

            conn.commit()
            st.success("Decision + snapshot saved ✅")
            st.info(f"System recommended vendor_id={recommended_vendor_id} | cheapest vendor_id={cheapest_vendor_id}")

            # ---- DB verification (for now, during development)
            st.subheader("Saved Record Check (DB)")

            check_df = pd.read_sql_query(
                """
                SELECT
                  d.rfq_id,
                  v.vendor_name AS selected_vendor,
                  d.selected_by,
                  d.override_reason,
                  d.created_on
                FROM rfq_decision d
                JOIN vendors v ON d.selected_vendor_id = v.vendor_id
                WHERE d.rfq_id = ?
                """,
                conn,
                params=(int(selected_rfq),)
            )

            snap_df = pd.read_sql_query(
                """
                SELECT
                  s.rfq_id,
                  v1.vendor_name AS recommended_vendor,
                  v2.vendor_name AS cheapest_vendor,
                  s.weights,
                  s.created_on
                FROM rfq_recommendation_snapshot s
                JOIN vendors v1 ON s.recommended_vendor_id = v1.vendor_id
                JOIN vendors v2 ON s.cheapest_vendor_id = v2.vendor_id
                WHERE s.rfq_id = ?
                """,
                conn,
                params=(int(selected_rfq),)
            )

            st.write("**Decision table:**")
            st.dataframe(check_df, use_container_width=True)

            st.write("**Recommendation snapshot table:**")
            st.dataframe(snap_df, use_container_width=True)

st.subheader("Current Saved Decision for this RFQ")

check_df = pd.read_sql_query(
    """
    SELECT
      d.rfq_id,
      v.vendor_name AS selected_vendor,
      d.selected_by,
      d.override_reason,
      d.created_on
    FROM rfq_decision d
    JOIN vendors v ON d.selected_vendor_id = v.vendor_id
    WHERE d.rfq_id = ?
    """,
    conn,
    params=(int(selected_rfq),)
)

snap_df = pd.read_sql_query(
    """
    SELECT
      s.rfq_id,
      v1.vendor_name AS recommended_vendor,
      v2.vendor_name AS cheapest_vendor,
      s.weights,
      s.created_on
    FROM rfq_recommendation_snapshot s
    JOIN vendors v1 ON s.recommended_vendor_id = v1.vendor_id
    JOIN vendors v2 ON s.cheapest_vendor_id = v2.vendor_id
    WHERE s.rfq_id = ?
    """,
    conn,
    params=(int(selected_rfq),)
)

st.write("**Decision:**")
st.dataframe(check_df, use_container_width=True)

st.write("**Snapshot:**")
st.dataframe(snap_df, use_container_width=True)          

conn.close()