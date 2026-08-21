"""
Streamlit-aware data loaders for the Biwenger dashboard.

This module owns all @st.cache_data wrappers and enrichment transforms.
Pages import from here, not from queries.py directly, so that:
  - cache is shared across pages in the same Streamlit process;
  - enrichment logic (display names, computed columns) is defined once.

queries.py stays as a pure, testable Supabase layer with no Streamlit dependency.
"""

import pandas as pd
import streamlit as st

from dashboard.queries import (
    fetch_all_player_matches,
    fetch_all_player_stats,
    fetch_all_value_history,
    fetch_current_team,
    fetch_player_stat_seasons,
    fetch_stats_history_for_players,
    fetch_value_history_for_slugs,
    fetch_value_player_index,
)

# ── Shared helpers ────────────────────────────────────────────────────────────


def make_display_name(df: pd.DataFrame) -> pd.Series:
    """Return a 'Player Name (Team)' label series, falling back to player_name or slug."""
    return df.apply(
        lambda r: (
            f"{r['player_name']} ({r['team']})"
            if pd.notna(r.get("player_name")) and pd.notna(r.get("team"))
            else (r.get("player_name") or r.get("slug", "Unknown"))
        ),
        axis=1,
    )


# ── Player index (dropdown population) ───────────────────────────────────────


@st.cache_data(ttl=300)
def load_player_index() -> pd.DataFrame:
    """
    One row per player from biwenger_player_value.
    Columns: slug, player_name, team, date, display_name.
    Cheap: only 4 columns fetched, paginated, deduped to one row per slug.
    """
    df = fetch_value_player_index()
    if df.empty:
        return df
    df["display_name"] = make_display_name(df)
    return df


# ── Value history (market trends page) ───────────────────────────────────────


@st.cache_data(ttl=300)
def load_value_history(slugs: tuple[str, ...], cutoff: str | None) -> pd.DataFrame:
    """
    Market-value rows for the given slugs, server-filtered by cutoff date.
    Adds: display_name, value_change_1d.
    Cache key: (slugs, cutoff) — changes correctly when window or selection changes.
    """
    df = fetch_value_history_for_slugs(list(slugs), cutoff_date=cutoff)
    if df.empty:
        return df
    df["display_name"] = make_display_name(df)
    df = df.sort_values(["slug", "date"]).copy()
    df["value_change_1d"] = df.groupby("slug")["market_value_eur"].diff()
    return df


# ── Stats history (market signal metrics) ────────────────────────────────────


@st.cache_data(ttl=300)
def load_stats_history(player_names: tuple[str, ...], cutoff: str | None) -> pd.DataFrame:
    """
    All stats snapshots (one per scrape date) for the given player names.
    Adds: display_name, ratio_purchase_sales.
    Uses player_name as the join key — slug is not yet backfilled in stats.
    Cache key: (player_names, cutoff).
    """
    df = fetch_stats_history_for_players(list(player_names), cutoff_date=cutoff)
    if df.empty:
        return df
    df["display_name"] = make_display_name(df)
    df["ratio_purchase_sales"] = (df["market_purchases_pct"] / df["market_sales_pct"].replace(0, pd.NA)).round(2)
    return df


@st.cache_data(ttl=300)
def load_latest_market_stats() -> pd.DataFrame:
    """
    Latest stats snapshot per player (all players, any season), with
    display_name and ratio_purchase_sales added.

    Used by the "similar players" ratio-proximity search on the Market
    Trends page. Only rows with a real slug are kept, so results line up
    with the value-history player index used elsewhere on that page.
    """
    df = fetch_all_player_stats(season=None)
    if df.empty:
        return df
    df = df[df["slug"].notna() & (df["slug"].str.strip() != "")].copy()
    if df.empty:
        return df
    df["display_name"] = make_display_name(df)
    df["ratio_purchase_sales"] = (df["market_purchases_pct"] / df["market_sales_pct"].replace(0, pd.NA)).round(2)
    return df


# ── Full-table loads (raw-data tabs in app.py) ────────────────────────────────


@st.cache_data(ttl=300)
def load_player_stat_seasons() -> pd.DataFrame:
    """Available player-stat seasons with their latest snapshot date."""
    return fetch_player_stat_seasons()


@st.cache_data(ttl=300)
def load_all_player_stats(season: str | None = None) -> pd.DataFrame:
    """Latest stats snapshot per player for the selected season, scoped to SofaScore."""
    return fetch_all_player_stats(season=season)


@st.cache_data(ttl=300)
def load_current_team() -> pd.DataFrame:
    """Current squad snapshot (replace-every-run state)."""
    return fetch_current_team()


@st.cache_data(ttl=300)
def load_all_matches() -> pd.DataFrame:
    """Full match history, scoped to SofaScore. Paginated."""
    return fetch_all_player_matches()


@st.cache_data(ttl=300)
def load_all_value_history() -> pd.DataFrame:
    """Full value history. Paginated. Use only for raw table display."""
    return fetch_all_value_history()
