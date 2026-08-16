"""
Read-only Supabase query helpers for the Biwenger dashboard.

All helpers are scoped to the SofaScore scoring system and return
pandas DataFrames. No writes, deletes, or DDL are performed here.
"""

import pandas as pd

from supabase_client.connection import get_supabase_backend_read_client

SCORING_SYSTEM = "sofascore"

STATS_TABLE = "biwenger_player_stats"
MATCHES_TABLE = "biwenger_player_matches"
VALUE_TABLE = "biwenger_player_value"
CURRENT_TEAM_TABLE = "biwenger_current_team"


def _client(supabase=None):
    return supabase if supabase is not None else get_supabase_backend_read_client()


def _paginate(query_factory, page_size: int = 1000) -> list[dict]:
    """Page through all rows of a Supabase query in ``page_size`` chunks.

    ``query_factory`` must be a zero-argument callable that returns a fresh
    Supabase query builder each time (so ``.range()`` can be appended per
    page without mutating a shared object).
    """
    all_rows: list[dict] = []
    offset = 0
    while True:
        result = query_factory().range(offset, offset + page_size - 1).execute()
        all_rows.extend(result.data)
        if len(result.data) < page_size:
            break
        offset += page_size
    return all_rows


def fetch_player_stat_seasons(supabase=None) -> pd.DataFrame:
    """
    Return available player-stat seasons with their latest snapshot date.

    The result is one row per non-null ``season``, scoped to SofaScore, sorted
    with the newest season snapshot first.
    """
    client = _client(supabase)
    rows = _paginate(
        lambda: (
            client.table(STATS_TABLE)
            .select("season, as_of_date")
            .eq("scoring_system", SCORING_SYSTEM)
            .order("as_of_date", desc=True)
        )
    )
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["as_of_date"] = pd.to_datetime(df["as_of_date"])
    df = df.dropna(subset=["season"])
    return df.sort_values("as_of_date", ascending=False).drop_duplicates(subset=["season"]).reset_index(drop=True)


def fetch_all_player_stats(
    supabase=None,
    *,
    season: str | None = None,
) -> pd.DataFrame:
    """
    Return the most recent stats snapshot per player (by slug where present,
    else by player_name + team), scoped to SofaScore.

    When ``season`` is provided, rows are limited to that Biwenger season and
    each player resolves to the latest available snapshot in that season.

    Full table is returned — callers filter locally.
    """
    client = _client(supabase)
    query = client.table(STATS_TABLE).select("*").eq("scoring_system", SCORING_SYSTEM)
    if season:
        query = query.eq("season", season)
    response = query.order("as_of_date", desc=True).execute()
    df = pd.DataFrame(response.data)
    if df.empty:
        return df

    # Keep only the latest snapshot per player identity.
    df["as_of_date"] = pd.to_datetime(df["as_of_date"])
    has_slug = df["slug"].notna() & (df["slug"].str.strip() != "")
    slug_rows = df[has_slug]
    legacy_rows = df[~has_slug]

    latest_slug = slug_rows.sort_values("as_of_date", ascending=False).drop_duplicates(subset=["slug"])

    if legacy_rows.empty:
        return latest_slug.reset_index(drop=True)

    # Exclude players already covered by a slugged row so a player with mixed
    # slug/null rows (e.g. Mbappé) does not appear twice.
    slug_player_keys = set(zip(latest_slug["player_name"].str.strip(), latest_slug["team"].str.strip()))
    legacy_keep_mask = ~legacy_rows.apply(
        lambda r: (str(r["player_name"]).strip(), str(r["team"]).strip()) in slug_player_keys,
        axis=1,
    )
    legacy_rows = legacy_rows.loc[legacy_keep_mask]

    if legacy_rows.empty:
        return latest_slug.reset_index(drop=True)

    latest_legacy = legacy_rows.sort_values("as_of_date", ascending=False).drop_duplicates(
        subset=["player_name", "team"]
    )

    return pd.concat([latest_slug, latest_legacy], ignore_index=True).reset_index(drop=True)


def fetch_current_team(supabase=None) -> pd.DataFrame:
    """
    Return the full current-team snapshot (latest replace-every-run state).
    """
    client = _client(supabase)
    response = client.table(CURRENT_TEAM_TABLE).select("*").order("created_at", desc=True).execute()
    return pd.DataFrame(response.data)


def fetch_player_roster(supabase=None) -> pd.DataFrame:
    """
    Return one row per slugged player (slug, player_name, team, position)
    from the most recent SofaScore stats snapshot.

    Used to populate player-selector dropdowns. Much cheaper than loading
    the full value-history table.
    """
    client = _client(supabase)
    response = (
        client.table(STATS_TABLE)
        .select("slug, player_name, team, position")
        .eq("scoring_system", SCORING_SYSTEM)
        .not_.is_("slug", "null")
        .order("as_of_date", desc=True)
        .execute()
    )
    df = pd.DataFrame(response.data)
    if df.empty:
        return df
    # One row per slug — keep the most recent stats snapshot.
    return df.drop_duplicates(subset=["slug"]).reset_index(drop=True)


def fetch_value_history_for_slugs(
    slugs: list[str],
    cutoff_date: str | None = None,
    supabase=None,
) -> pd.DataFrame:
    """
    Return market-value rows for the given slugs, optionally filtered to
    dates on or after ``cutoff_date`` (ISO string, e.g. ``"2026-06-21"``).

    Paginates automatically so no rows are silently dropped.
    """
    client = _client(supabase)

    def _q():
        q = client.table(VALUE_TABLE).select("*").in_("slug", slugs)
        if cutoff_date:
            q = q.gte("date", cutoff_date)
        return q.order("date", desc=False)

    rows = _paginate(_q)
    df = pd.DataFrame(rows)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df


def fetch_all_player_matches(supabase=None) -> pd.DataFrame:
    """
    Return full match history scoped to SofaScore.
    Paginates automatically so no rows are silently dropped.
    Full table is returned — callers filter locally.
    """
    client = _client(supabase)
    rows = _paginate(
        lambda: (
            client.table(MATCHES_TABLE).select("*").eq("scoring_system", SCORING_SYSTEM).order("match_date", desc=True)
        )
    )
    return pd.DataFrame(rows)


def fetch_value_player_index(supabase=None) -> pd.DataFrame:
    """
    Return one row per player from ``biwenger_player_value``, containing only
    ``slug``, ``player_name``, and ``team``.

    Used to populate the player-selector dropdown cheaply — three columns
    instead of the full 118K-row table.  Deduplication keeps the most recent
    row per slug (latest ``date``), which gives the up-to-date team name.
    """
    client = _client(supabase)
    rows = _paginate(lambda: client.table(VALUE_TABLE).select("slug, player_name, team, date").order("date", desc=True))
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    # Most-recent row per slug → gives current team name.
    return df.drop_duplicates(subset=["slug"]).reset_index(drop=True)


def fetch_stats_history_for_players(
    player_names: list[str],
    cutoff_date: str | None = None,
    supabase=None,
) -> pd.DataFrame:
    """
    Return all stats snapshots for the given player names (one row per scrape
    date), scoped to SofaScore.

    Uses player_name as the join key because slug is not yet backfilled for
    most rows in biwenger_player_stats. Once slugs are backfilled, this query
    can be extended to prefer slug-based lookup.
    """
    client = _client(supabase)
    q = (
        client.table(STATS_TABLE)
        .select("slug, player_name, team, as_of_date, market_purchases_pct, market_sales_pct")
        .eq("scoring_system", SCORING_SYSTEM)
        .in_("player_name", player_names)
    )
    if cutoff_date:
        q = q.gte("as_of_date", cutoff_date)
    response = q.order("as_of_date", desc=False).execute()
    df = pd.DataFrame(response.data)
    if not df.empty:
        df["as_of_date"] = pd.to_datetime(df["as_of_date"])
    return df


def fetch_all_value_history(supabase=None) -> pd.DataFrame:
    """
    Return full market-value history from biwenger_player_value.
    Paginates automatically so no rows are silently dropped.
    Full table is returned — callers filter locally.
    """
    client = _client(supabase)
    rows = _paginate(lambda: client.table(VALUE_TABLE).select("*").order("date", desc=True))
    return pd.DataFrame(rows)
