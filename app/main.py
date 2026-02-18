import streamlit as st
from app.db.schema import create_tables
from app.db.seed import is_seeded, seed_demo_data

st.set_page_config(page_title="ProcureLive", layout="wide")

# Ensure DB + tables exist
create_tables()

# Seed demo data only if empty (development)
if not is_seeded():
    seed_demo_data()

st.title("ProcureLive (Prototype)")
st.caption("Real-time Procurement Visibility for CMD")

st.write("Use the pages on the left sidebar to navigate.")
st.success("Database ready ✅")