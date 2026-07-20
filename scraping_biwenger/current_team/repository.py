import pandas as pd

from supabase_client.utils import check_if_table_exists, insert_rows_into_table


def current_team_table_exists(supabase, table_name: str) -> bool:
    return check_if_table_exists(supabase, table_name)


def clear_current_team_snapshot(supabase, table_name: str) -> None:
    """
    Remove all rows from the current-state squad snapshot table.
    """
    supabase.table(table_name).delete().neq("id", 0).execute()


def insert_current_team_rows(supabase, table_name: str, df: pd.DataFrame) -> None:
    rows = df.astype(object).where(pd.notna(df), None).to_dict(orient="records")
    insert_rows_into_table(supabase, table_name=table_name, rows=rows)
