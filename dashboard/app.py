"""
Biwenger read-only dashboard.

Run with:
    streamlit run dashboard/app.py
"""

import streamlit as st

from dashboard.data import (
    load_all_matches,
    load_all_player_stats,
    load_all_value_history,
    load_current_team,
)

st.set_page_config(page_title="Biwenger Dashboard", layout="wide")
st.title("Biwenger Dashboard")
st.caption("Read-only view. All stats use the SofaScore scoring system.")

# ── Tabs ──────────────────────────────────────────────────────────────────────

tab_stats, tab_team, tab_matches, tab_value = st.tabs(
    ["Player Stats", "Current Team", "Match History", "Value History"]
)

# ── Player Stats ──────────────────────────────────────────────────────────────
with tab_stats:
    st.subheader("Latest Player Stats")
    with st.spinner("Loading…"):
        df_stats = load_all_player_stats()
    if df_stats.empty:
        st.info("No player stats found.")
    else:
        st.dataframe(df_stats, width="stretch")

# ── Current Team ──────────────────────────────────────────────────────────────
with tab_team:
    st.subheader("Current Team Snapshot")
    with st.spinner("Loading…"):
        df_team = load_current_team()
    if df_team.empty:
        st.info("No current-team data found.")
    else:
        st.dataframe(df_team, width="stretch")

# ── Match History ─────────────────────────────────────────────────────────────
with tab_matches:
    st.subheader("Match History")
    slug_filter = st.text_input("Filter by player slug (leave blank for all)")
    with st.spinner("Loading…"):
        df_matches = load_all_matches()
    if slug_filter:
        df_matches = df_matches[df_matches["slug"] == slug_filter]
    if df_matches.empty:
        st.info("No match rows found.")
    else:
        st.dataframe(df_matches, width="stretch")

# ── Value History ─────────────────────────────────────────────────────────────
with tab_value:
    st.subheader("Market Value History")
    slug_filter_val = st.text_input("Filter by player slug (leave blank for all)", key="val_slug")
    with st.spinner("Loading…"):
        df_value = load_all_value_history()
    if slug_filter_val:
        df_value = df_value[df_value["slug"] == slug_filter_val]
    if df_value.empty:
        st.info("No value history found.")
    else:
        st.dataframe(df_value, width="stretch")
