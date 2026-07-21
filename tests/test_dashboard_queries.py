"""
Integration tests for dashboard read-only query helpers.

These tests require a live Supabase connection and valid secrets/supabase.toml.
They are marked with @pytest.mark.integration and are excluded from `make ci`.

Run manually with:
    pytest -m integration tests/test_dashboard_queries.py
"""

import pytest

from dashboard.queries import (
    fetch_all_player_matches,
    fetch_all_player_stats,
    fetch_all_value_history,
    fetch_current_team,
)


@pytest.mark.integration
def test_fetch_all_player_stats_returns_dataframe():
    df = fetch_all_player_stats()
    # Returns a DataFrame (may be empty if DB has no rows yet)
    assert hasattr(df, "columns")
    if not df.empty:
        assert "player_name" in df.columns
        assert "as_of_date" in df.columns
        # Every row must be SofaScore — confirmed by query filter, verified here
        assert (df["scoring_system"] == "SofaScore").all()
        # No duplicate slug entries in the result
        slug_rows = df[df["slug"].notna() & (df["slug"].str.strip() != "")]
        assert slug_rows["slug"].is_unique


@pytest.mark.integration
def test_fetch_current_team_returns_dataframe():
    df = fetch_current_team()
    assert hasattr(df, "columns")
    if not df.empty:
        assert "name" in df.columns
        assert "market_value" in df.columns


@pytest.mark.integration
def test_fetch_all_player_matches_returns_dataframe():
    df = fetch_all_player_matches()
    assert hasattr(df, "columns")
    if not df.empty:
        assert "slug" in df.columns
        assert "match_date" in df.columns
        assert (df["scoring_system"] == "SofaScore").all()


@pytest.mark.integration
def test_fetch_all_player_matches_local_slug_filter():
    # Fetch all then filter locally — mirrors the app pattern
    df_all = fetch_all_player_matches()
    if df_all.empty or df_all["slug"].dropna().empty:
        pytest.skip("No slugged match rows in DB — skipping slug-filter test")

    test_slug = df_all["slug"].dropna().iloc[0]
    df_filtered = df_all[df_all["slug"] == test_slug]
    assert not df_filtered.empty
    assert (df_filtered["slug"] == test_slug).all()


@pytest.mark.integration
def test_fetch_all_value_history_returns_dataframe():
    df = fetch_all_value_history()
    assert hasattr(df, "columns")
    if not df.empty:
        assert "slug" in df.columns
        assert "market_value_eur" in df.columns
        assert "date" in df.columns


@pytest.mark.integration
def test_fetch_all_value_history_local_slug_filter():
    # Fetch all then filter locally — mirrors the app pattern
    df_all = fetch_all_value_history()
    if df_all.empty:
        pytest.skip("No value history rows in DB — skipping slug-filter test")

    test_slug = df_all["slug"].iloc[0]
    df_filtered = df_all[df_all["slug"] == test_slug]
    assert not df_filtered.empty
    assert (df_filtered["slug"] == test_slug).all()
