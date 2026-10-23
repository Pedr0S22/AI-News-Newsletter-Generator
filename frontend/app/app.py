import streamlit as st
from client import client

st.set_page_config(
    page_title="AI News - System Health",
    page_icon="🤖",
    layout="centered",
)

st.title("🤖 AI News Generator — Health Dashboard")
st.caption(f"Testing connectivity to Backend at: `{client.base_url}`")

if st.button("🔄 Refresh Status"):
    st.rerun()

is_healthy, payload, err = client.check_health()

if is_healthy and payload:
    st.success("Backend API is online and healthy!", icon="🟢")
    st.json(payload)
else:
    st.error(f"Cannot reach Backend API at `{client.base_url}`", icon="🔴")
    if err:
        st.code(err, language="text")
    st.info("Ensure the backend service is running (`docker compose up` or `uv run uvicorn api.main:app`).")
