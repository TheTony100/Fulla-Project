from __future__ import annotations

import streamlit as st

from database.db import get_connection, init_db
from ui.dashboard import render_dashboard

st.set_page_config(
    page_title="FOHF Report Extraction MVP",
    layout="wide",
    initial_sidebar_state="collapsed",
)

conn = get_connection()
init_db(conn)
render_dashboard(conn)

