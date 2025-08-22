from typing import List, Dict
from postgrest.exceptions import APIError

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