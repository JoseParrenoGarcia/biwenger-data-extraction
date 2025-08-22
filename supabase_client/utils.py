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
