"""
Simple Streamlit dashboard starter.
Run with:
    streamlit run dashboards/app.py
"""

import streamlit as st

st.set_page_config(page_title="Project Dashboard", layout="wide")

st.title("Project Dashboard")
st.write("Use this dashboard to present your data science project.")
st.info("Add charts, metrics, model results, and explanations here.")
