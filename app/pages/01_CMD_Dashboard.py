import streamlit as st
import pandas as pd
from app.db.database import get_connection

st.set_page_config(page_title="CMD Dashboard", layout="wide")

st.title("CMD Dashboard")
st.caption("Live view of PR → RFQ → Quotes")

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
st.subheader("Open RFQs: Vendor Quotes (sorted by price)")
st.dataframe(df_view, use_container_width=True)

st.subheader("Cheapest vs Recommended (Explainable)")
summary = cheapest.merge(recommended, on="rfq_id", how="left")
st.dataframe(summary, use_container_width=True)

st.subheader("Quick Risk Flags")
df_flags = df_view.copy()
df_flags["flag_high_risk"] = df_flags["risk_rating"].apply(lambda x: "⚠️ High Risk Vendor" if x == "High" else "")

# Cheapest tag per RFQ
df_flags["rank_price"] = df_flags.groupby("rfq_id")["price"].rank(method="dense")
df_flags["flag_low_price"] = df_flags["rank_price"].apply(lambda r: "💰 Cheapest" if r == 1 else "")

st.dataframe(
    df_flags[
        ["rfq_id", "rm_name", "vendor_name", "risk_rating", "price", "lead_time_days", "flag_low_price", "flag_high_risk", "notes"]
    ],
    use_container_width=True
)