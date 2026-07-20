from typing import List, Dict, Iterable, Any
from postgrest.exceptions import APIError
import hashlib
import itertools
import time

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
        supabase.table(table_name).insert(rows).execute()
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
