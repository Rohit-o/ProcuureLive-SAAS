import streamlit as st
import pandas as pd
from app.db.database import get_connection

st.set_page_config(page_title="CMD Dashboard", layout="wide")

st.title("Dashboard")
st.caption("Live procurement governance: system recommendation vs purchase decision")

conn = get_connection()

# KPI cards
k1 = pd.read_sql_query("SELECT COUNT(*) as cnt FROM pr WHERE status='Open'", conn)["cnt"][0]
k2 = pd.read_sql_query("SELECT COUNT(*) as cnt FROM rfq WHERE status='Open'", conn)["cnt"][0]
k3 = pd.read_sql_query("SELECT COUNT(*) as cnt FROM quotes", conn)["cnt"][0]

c1, c2, c3 = st.columns(3)
c1.metric("Open PRs", int(k1))
c2.metric("Open RFQs", int(k2))
c3.metric("Total Quotes", int(k3))

st.divider()

query = """
SELECT
  rfq.rfq_id,
  pr.pr_id,
  rm.rm_name,
  pr.qty,
  pr.need_by,
  pr.site,
  v.vendor_name,
  v.risk_rating,
  q.price,
  q.lead_time_days,
  q.payment_terms,
  q.validity_days,
  q.notes
FROM quotes q
JOIN rfq ON q.rfq_id = rfq.rfq_id
JOIN pr  ON rfq.pr_id = pr.pr_id
JOIN rm_master rm ON pr.rm_id = rm.rm_id
JOIN vendors v ON q.vendor_id = v.vendor_id
ORDER BY rfq.rfq_id, q.price ASC
"""

df = pd.read_sql_query(query, conn)
conn.close()

st.subheader("Compact Governance View (System vs Purchase)")
conn = get_connection()
cmd_df = pd.read_sql_query(
    """
    SELECT
      rfq.rfq_id,
      pr.pr_id,
      rm.rm_name,
      vcheap.vendor_name AS cheapest_vendor,
      vrec.vendor_name   AS recommended_vendor,
      vsel.vendor_name   AS selected_vendor,
      d.selected_by,
      d.override_reason,
      d.created_on AS decision_time
    FROM rfq
    JOIN pr ON rfq.pr_id = pr.pr_id
    JOIN rm_master rm ON pr.rm_id = rm.rm_id
    LEFT JOIN rfq_recommendation_snapshot s ON s.rfq_id = rfq.rfq_id
    LEFT JOIN vendors vcheap ON s.cheapest_vendor_id = vcheap.vendor_id
    LEFT JOIN vendors vrec   ON s.recommended_vendor_id = vrec.vendor_id
    LEFT JOIN rfq_decision d ON d.rfq_id = rfq.rfq_id
    LEFT JOIN vendors vsel   ON d.selected_vendor_id = vsel.vendor_id
    ORDER BY rfq.rfq_id DESC
    """,
    conn
)
conn.close()

if cmd_df.empty:
    st.info("No decisions/snapshots saved yet. Use 'Make Decision' page to record selection.")
else:
    # Filters (compact)
    cA, cB = st.columns(2)
    with cA:
        pr_filter = st.selectbox("Filter by PR", options=["All"] + cmd_df["pr_id"].dropna().astype(int).unique().tolist())
    with cB:
        rfq_filter = st.selectbox("Filter by RFQ", options=["All"] + cmd_df["rfq_id"].dropna().astype(int).unique().tolist())

    view = cmd_df.copy()
    if pr_filter != "All":
        view = view[view["pr_id"] == int(pr_filter)]
    if rfq_filter != "All":
        view = view[view["rfq_id"] == int(rfq_filter)]

    view["deviation"] = view.apply(
        lambda r: (
            "⏳ Pending" if pd.isna(r["selected_vendor"])
            else ("✅ Match" if r["selected_vendor"] == r["recommended_vendor"] else "⚠️ Deviated")
        ),
        axis=1
    )

    st.dataframe(
        view[
            [
                "rfq_id",
                "pr_id",
                "rm_name",
                "cheapest_vendor",
                "recommended_vendor",
                "selected_vendor",
                "deviation",
                "override_reason",
                "selected_by",
                "decision_time",
            ]
        ],
        use_container_width=True
    )

st.divider()

# ---------------------------
# RFQ Filter
# ---------------------------
rfq_list = sorted(df["rfq_id"].unique().tolist())
selected_rfq = st.selectbox("Select RFQ", options=["All"] + rfq_list)

if selected_rfq != "All":
    df_view = df[df["rfq_id"] == selected_rfq].copy()
else:
    df_view = df.copy()

# ---------------------------
# Scoring: Cheapest vs Recommended
# ---------------------------
def normalize_inverse(series: pd.Series) -> pd.Series:
    """Return 0-100 where smaller input values are better (price, lead time)."""
    min_v = float(series.min())
    max_v = float(series.max())
    if max_v == min_v:
        return series.apply(lambda _: 100.0)
    return (max_v - series) / (max_v - min_v) * 100.0

def risk_penalty(risk: str) -> float:
    return {"Low": 0.0, "Medium": -15.0, "High": -40.0}.get(risk, -15.0)

# Cheapest per RFQ
cheapest = (
    df_view.sort_values(["rfq_id", "price"], ascending=[True, True])
    .groupby("rfq_id", as_index=False)
    .first()[["rfq_id", "vendor_name", "price", "risk_rating", "lead_time_days"]]
).rename(columns={
    "vendor_name": "cheapest_vendor",
    "price": "cheapest_price",
    "risk_rating": "cheapest_risk",
    "lead_time_days": "cheapest_lead_time_days"
})

# Recommended per RFQ (explainable scoring)
df_sc = df_view.copy()
df_sc["price_score"] = df_sc.groupby("rfq_id")["price"].transform(normalize_inverse)
df_sc["lt_score"] = df_sc.groupby("rfq_id")["lead_time_days"].transform(normalize_inverse)
df_sc["risk_penalty"] = df_sc["risk_rating"].apply(risk_penalty)
df_sc["final_score"] = 0.65 * df_sc["price_score"] + 0.35 * df_sc["lt_score"] + df_sc["risk_penalty"]

recommended = (
    df_sc.sort_values(["rfq_id", "final_score"], ascending=[True, False])
    .groupby("rfq_id", as_index=False)
    .first()[["rfq_id", "vendor_name", "final_score", "price", "risk_rating", "lead_time_days"]]
).rename(columns={
    "vendor_name": "recommended_vendor",
    "price": "recommended_price",
    "risk_rating": "recommended_risk",
    "lead_time_days": "recommended_lead_time_days"
})

# ---------------------------
# Display
# ---------------------------

# Trust panel (always available, not cluttering)
with st.expander("Why Recommended (Score Breakdown)", expanded=False):
    st.dataframe(
        df_sc[
            [
                "rfq_id",
                "rm_name",
                "vendor_name",
                "price",
                "lead_time_days",
                "risk_rating",
                "price_score",
                "lt_score",
                "risk_penalty",
                "final_score",
            ]
        ].sort_values(["rfq_id", "final_score"], ascending=[True, False]),
        use_container_width=True
    )

# Details (hide long tables by default)
show_details = st.checkbox("Show detailed quotes & risk flags", value=False)

if show_details:
    st.subheader("Vendor Quotes (Details)")
    st.dataframe(df_view, use_container_width=True)

    st.subheader("Risk Flags (Details)")
    df_flags = df_view.copy()
    df_flags["flag_high_risk"] = df_flags["risk_rating"].apply(
        lambda x: "⚠️ High Risk Vendor" if x == "High" else ""
    )

    # Cheapest tag per RFQ
    df_flags["rank_price"] = df_flags.groupby("rfq_id")["price"].rank(method="dense")
    df_flags["flag_low_price"] = df_flags["rank_price"].apply(lambda r: "💰 Cheapest" if r == 1 else "")

    st.dataframe(
        df_flags[
            [
                "rfq_id",
                "rm_name",
                "vendor_name",
                "risk_rating",
                "price",
                "lead_time_days",
                "flag_low_price",
                "flag_high_risk",
                "notes",
            ]
        ],
        use_container_width=True
    )