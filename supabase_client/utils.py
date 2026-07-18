from typing import List, Dict, Iterable, Any, Union
from postgrest.exceptions import APIError
import hashlib
import itertools
import time
import pandas as pd
import math

def _batched(iterable, n):
    """Fallback if Python <3.12. Your 3.13 has itertools.batched, but keep this for safety."""
    it = iter(iterable)
    while True:
        chunk = list(itertools.islice(it, n))
        if not chunk:
            return
        yield chunk

def check_if_table_exists(supabase, table_name: str) -> bool:
    """
    Returns True if the table exists in the public schema, False otherwise.
    """
    try:
        supabase.table(table_name).select("*").limit(1).execute()
        return True
    except APIError as e:
        if "Could not find the table" in str(e):
            return False
        raise

def insert_rows_into_table(supabase, table_name: str, rows: List[Dict]) -> None:
    """
    Inserts a list of dictionaries into the given Supabase table.

    Args:
        supabase: Supabase client instance.
        table_name (str): Table to insert into.
        rows (List[Dict]): Each dict must match the table schema.

    Raises:
        Exception: If Supabase returns an error.
    """
    if not rows:
        print("⚠️ No rows to insert. Skipping.")
        return

    try:
        # Newer Supabase libraries might have slightly different error handling
        result = supabase.table(table_name).insert(rows).execute()
        print(f"✅ Inserted {len(rows)} rows into '{table_name}' successfully.")

    except Exception as e:
        # This will capture any errors during the insert operation
        raise Exception(f"❌ Supabase insert failed: {str(e)}")

def insert_rows_into_table_batched(
    supabase,
    table_name: str,
    rows: List[Dict],
    chunk_size: int = 5000,
    sleep_s: float = 0.25,
    returning: str = "minimal",
    json_sanitize: bool = True,
) -> None:
    """
    Insert many rows with batching to avoid statement timeouts.

    - returning="minimal" reduces payload.
    - json_sanitize: replaces NaN/NaT with None (JSON-safe).

    Raises on first failing chunk with the original error.
    """
    if not rows:
        print(f"⚠️ No rows to insert into '{table_name}'. Skipping.")
        return

    # JSON-safe (httpx doesn't allow NaN). Convert pandas-style <NA>/NaN/NaT → None.
    if json_sanitize:
        try:
            import pandas as pd  # optional; if not available, we silently skip
            if isinstance(rows, list) and rows and isinstance(rows[0], dict):
                df = pd.DataFrame(rows)
                df = df.where(df.notna(), None)
                rows = df.to_dict(orient="records")
        except Exception:
            pass

    # Prefer itertools.batched (py3.12+), otherwise _batched
    batched_iter = getattr(itertools, "batched", _batched)(rows, chunk_size)

    count = 0
    for chunk in batched_iter:
        try:
            supabase.table(table_name).insert(chunk, returning=returning).execute()
            count += len(chunk)
        except Exception as e:
            raise Exception(
                f"❌ Supabase batched insert failed after {count} rows "
                f"(chunk_size={chunk_size}) on table '{table_name}': {e}"
            )
        if sleep_s:
            time.sleep(sleep_s)
    print(f"✅ Inserted {count} rows into '{table_name}' (batched).")


def upsert_rows_into_table(supabase, table_name: str, rows: List[Dict], on_conflict: str) -> None:
    """
    Upserts rows into a Supabase table using a unique constraint/index on 'on_conflict'.
    """
    if not rows:
        print("⚠️ No rows to upsert. Skipping.")
        return
    try:
        supabase.table(table_name).upsert(rows, on_conflict=on_conflict).execute()
        print(f"✅ Upserted {len(rows)} rows into '{table_name}' (conflict target: {on_conflict}).")
    except Exception as e:
        raise Exception(f"❌ Supabase upsert failed: {str(e)}")

def compute_content_hash(row: Dict[str, Any], cols: Iterable[str]) -> str:
    def _norm_for_hash(v: Any) -> str:
        if v is None:
            return ""
        if isinstance(v, str):
            return v.strip()
        # For numerics, exact equality: cast to string (same as ::text in SQL)
        return str(v)

    parts = [_norm_for_hash(row.get(c)) for c in cols]
    payload = "|".join(parts)
    return hashlib.md5(payload.encode("utf-8")).hexdigest()

def fetch_existing_values_for_slug(
    supabase, table_name: str, slug: str, min_date: str, max_date: str, page_size: int = 2000
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
        if not data: break
        rows.extend(data)
        if len(data) < page_size: break
        start += page_size

    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=["date", "market_value_eur"])
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    df["market_value_eur"] = pd.to_numeric(df["market_value_eur"], errors="coerce")
    return df[["date", "market_value_eur"]]

def delete_rows_for_slug_dates(
    supabase, table_name: str, slug: str, dates: List[str]
) -> None:
    # dates is a small list (<= 365), safe for IN()
    if not dates: return
    supabase.table(table_name).delete().eq("slug", slug).in_("date", dates).execute()

def compute_value_delta_for_slug(
    new_df: pd.DataFrame,  # columns: date, market_value_eur, slug, (player_name, team)
    existing_df: pd.DataFrame,  # columns: date, market_value_eur
) -> pd.DataFrame:
    """
    Keep only rows where (date) doesn't exist in DB or value differs from DB.
    Assumes 'date' is 'YYYY-MM-DD' string and values are numeric.
    """
    if new_df.empty:
        return new_df

    # De-dup within the incoming set (keep last seen per date)
    new_df = (
        new_df.copy()
        .sort_values("date")
        .drop_duplicates(subset=["date"], keep="last")
    )
    # If DB empty → everything is delta
    if existing_df is None or existing_df.empty:
        return new_df

    merged = new_df.merge(
        existing_df.rename(columns={"market_value_eur": "market_value_eur_db"}),
        on="date",
        how="left",
    )
    delta = merged[
        merged["market_value_eur_db"].isna()
        | (merged["market_value_eur"] != merged["market_value_eur_db"])
    ].drop(columns=["market_value_eur_db"])
    return delta.reset_index(drop=True)

def delete_stats_for_player_team_day(
    supabase,
    table_name: str,
    player_name: str,
    team: str,
    as_of_date: str,
    scoring_system: str | None = None,
) -> None:
    query = supabase.table(table_name)\
        .delete()\
        .eq("player_name", player_name)\
        .eq("team", team)\
        .eq("as_of_date", as_of_date)
    if scoring_system is not None:
        query = query.eq("scoring_system", scoring_system)
    query.execute()

def delete_matches_for_player_dates(
    supabase,
    table_name: str,
    player_name: str,
    team: str,
    dates: List[str],
    scoring_system: str | None = None,
    chunk_size: int = 100,
) -> None:
    """
    Delete existing match rows for (player_name, team) limited to the given match_date list.
    - `dates` must be 'YYYY-MM-DD' strings (normalize before calling).
    - Chunked to keep the SQL IN() list small and avoid timeouts.
    """
    if not dates:
        return

    # dedupe + drop falsy
    uniq_dates = sorted({d for d in dates if d})

    for i in range(0, len(uniq_dates), chunk_size):
        batch = uniq_dates[i : i + chunk_size]
        query = supabase.table(table_name) \
            .delete() \
            .eq("player_name", player_name) \
            .eq("team", team) \
            .in_("match_date", batch)
        if scoring_system is not None:
            query = query.eq("scoring_system", scoring_system)
        query.execute()
