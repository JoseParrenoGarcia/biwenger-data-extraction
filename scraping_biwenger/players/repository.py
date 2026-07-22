from typing import Dict, List

import pandas as pd

from supabase_client.utils import check_if_table_exists, insert_rows_into_table_batched


def player_table_exists(supabase, table_name: str) -> bool:
    return check_if_table_exists(supabase, table_name)


def delete_stats_snapshot(
    supabase,
    table_name: str,
    slug: str,
    as_of_date: str,
    scoring_system: str | None = None,
) -> None:
    query = supabase.table(table_name).delete().eq("slug", slug).eq("as_of_date", as_of_date)
    if scoring_system is not None:
        query = query.eq("scoring_system", scoring_system)
    query.execute()


def delete_matches_for_season_identities(
    supabase,
    table_name: str,
    identities: List[Dict[str, str]],
    chunk_size: int = 100,
) -> None:
    """
    Delete exact season-aware match identities before inserting replacements.

    Required identity fields:
    - slug
    - season_label
    - round_label
    - match_date
    - scoring_system
    """
    clean_identities = [
        identity
        for identity in identities
        if identity.get("slug")
        and identity.get("season_label")
        and identity.get("round_label")
        and identity.get("match_date")
        and identity.get("scoring_system")
    ]
    if not clean_identities:
        return

    for i in range(0, len(clean_identities), chunk_size):
        for identity in clean_identities[i : i + chunk_size]:
            (
                supabase.table(table_name)
                .delete()
                .eq("slug", identity["slug"])
                .eq("season_label", identity["season_label"])
                .eq("round_label", identity["round_label"])
                .eq("match_date", identity["match_date"])
                .eq("scoring_system", identity["scoring_system"])
                .execute()
            )


def fetch_existing_value_history(
    supabase,
    table_name: str,
    slug: str,
    min_date: str,
    max_date: str,
    page_size: int = 2000,
) -> pd.DataFrame:
    rows: List[Dict] = []
    start = 0
    while True:
        res = (
            supabase.table(table_name)
            .select("date, market_value_eur")
            .eq("slug", slug)
            .gte("date", min_date)
            .lte("date", max_date)
            .range(start, start + page_size - 1)
            .execute()
        )
        data = getattr(res, "data", None) or []
        if not data:
            break
        rows.extend(data)
        if len(data) < page_size:
            break
        start += page_size

    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=["date", "market_value_eur"])
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    df["market_value_eur"] = pd.to_numeric(df["market_value_eur"], errors="coerce")
    return df[["date", "market_value_eur"]]


def delete_value_history_dates(
    supabase,
    table_name: str,
    slug: str,
    dates: List[str],
) -> None:
    if not dates:
        return
    supabase.table(table_name).delete().eq("slug", slug).in_("date", dates).execute()


def insert_player_rows_batched(
    supabase,
    table_name: str,
    rows: List[Dict],
    *,
    chunk_size: int = 1000,
    sleep_s: float = 0.03,
) -> None:
    insert_rows_into_table_batched(
        supabase,
        table_name=table_name,
        rows=rows,
        chunk_size=chunk_size,
        sleep_s=sleep_s,
        returning="minimal",
    )
