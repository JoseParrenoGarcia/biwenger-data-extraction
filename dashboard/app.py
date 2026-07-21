"""
Biwenger read-only dashboard.

Run with:
    streamlit run dashboard/app.py
"""

import streamlit as st

from dashboard.queries import (
    fetch_current_team,
    fetch_latest_player_stats,
    fetch_player_matches,
    fetch_value_history,
)

st.set_page_config(page_title="Biwenger Dashboard", layout="wide")
st.title("Biwenger Dashboard")
st.caption("Read-only view. All stats use the SofaScore scoring system.")

tab_stats, tab_team, tab_matches, tab_value = st.tabs(
    ["Player Stats", "Current Team", "Match History", "Value History"]
)

# ── Player Stats ──────────────────────────────────────────────────────────────
with tab_stats:
    st.subheader("Latest Player Stats")
    with st.spinner("Loading…"):
        df_stats = fetch_latest_player_stats()
    if df_stats.empty:
        st.info("No player stats found.")
    else:
        st.dataframe(df_stats, use_container_width=True)

# ── Current Team ──────────────────────────────────────────────────────────────
with tab_team:
    st.subheader("Current Team Snapshot")
    with st.spinner("Loading…"):
        df_team = fetch_current_team()
    if df_team.empty:
        st.info("No current-team data found.")
    else:
        st.dataframe(df_team, use_container_width=True)

# ── Match History ─────────────────────────────────────────────────────────────
with tab_matches:
    st.subheader("Match History")
    slug_filter = st.text_input("Filter by player slug (leave blank for all)")
    with st.spinner("Loading…"):
        df_matches = fetch_player_matches(slug=slug_filter or None)
    if df_matches.empty:
        st.info("No match rows found.")
    else:
        st.dataframe(df_matches, use_container_width=True)

# ── Value History ─────────────────────────────────────────────────────────────
with tab_value:
    st.subheader("Market Value History")
    slug_filter_val = st.text_input("Filter by player slug (leave blank for all)", key="val_slug")
    with st.spinner("Loading…"):
        df_value = fetch_value_history(slug=slug_filter_val or None)
    if df_value.empty:
        st.info("No value history found.")
    else:
        st.dataframe(df_value, use_container_width=True)
