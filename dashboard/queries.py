"""
Read-only Supabase query helpers for the Biwenger dashboard.

All helpers are scoped to the SofaScore scoring system and return
pandas DataFrames. No writes, deletes, or DDL are performed here.
"""

import pandas as pd

from supabase_client.connection import get_supabase_client

SCORING_SYSTEM = "SofaScore"

STATS_TABLE = "biwenger_player_stats"
MATCHES_TABLE = "biwenger_player_matches"
VALUE_TABLE = "biwenger_player_value"
CURRENT_TEAM_TABLE = "biwenger_current_team"


def _client(supabase=None):
    return supabase if supabase is not None else get_supabase_client()


def fetch_latest_player_stats(supabase=None) -> pd.DataFrame:
    """
    Return the most recent stats snapshot per player (by slug where present,
    else by player_name + team), scoped to SofaScore.
    """
    client = _client(supabase)
    response = (
        client.table(STATS_TABLE)
        .select("*")
        .eq("scoring_system", SCORING_SYSTEM)
        .order("as_of_date", desc=True)
        .execute()
    )
    df = pd.DataFrame(response.data)
    if df.empty:
        return df

    # Keep only the latest snapshot per player identity.
    df["as_of_date"] = pd.to_datetime(df["as_of_date"])
    slug_rows = df[df["slug"].notna() & (df["slug"].str.strip() != "")]
    legacy_rows = df[df["slug"].isna() | (df["slug"].str.strip() == "")]

    latest_slug = slug_rows.sort_values("as_of_date", ascending=False).drop_duplicates(subset=["slug"])
    latest_legacy = legacy_rows.sort_values("as_of_date", ascending=False).drop_duplicates(
        subset=["player_name", "team"]
    )

    return pd.concat([latest_slug, latest_legacy], ignore_index=True)


def fetch_current_team(supabase=None) -> pd.DataFrame:
    """
    Return the full current-team snapshot (latest replace-every-run state).
    """
    client = _client(supabase)
    response = client.table(CURRENT_TEAM_TABLE).select("*").order("created_at", desc=True).execute()
    return pd.DataFrame(response.data)


def fetch_player_matches(supabase=None, slug: str | None = None) -> pd.DataFrame:
    """
    Return match history scoped to SofaScore.
    Optionally filter to a single player by slug.
    """
    client = _client(supabase)
    query = client.table(MATCHES_TABLE).select("*").eq("scoring_system", SCORING_SYSTEM)
    if slug is not None:
        query = query.eq("slug", slug)
    response = query.order("match_date", desc=True).execute()
    return pd.DataFrame(response.data)


def fetch_value_history(supabase=None, slug: str | None = None) -> pd.DataFrame:
    """
    Return market-value history from biwenger_player_value.
    Optionally filter to a single player by slug.
    """
    client = _client(supabase)
    query = client.table(VALUE_TABLE).select("*")
    if slug is not None:
        query = query.eq("slug", slug)
    response = query.order("date", desc=True).execute()
    return pd.DataFrame(response.data)
