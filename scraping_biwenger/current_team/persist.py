import pandas as pd

from supabase_client.connection import get_supabase_client
from supabase_client.utils import check_if_table_exists, insert_rows_into_table

from scraping_biwenger.current_team.transform import validate_current_team_payload


DEFAULT_CURRENT_TEAM_TABLE = "biwenger_current_team"


def missing_table_message(table_name: str) -> str:
    return (
        f"Supabase table '{table_name}' does not exist. "
        "Run the schema bootstrap before uploading data."
    )


def replace_current_team(
    df: pd.DataFrame,
    table_name: str = DEFAULT_CURRENT_TEAM_TABLE,
    logger=None,
) -> None:
    """
    Replace the current-team table contents with the latest scraped snapshot.
    """
    supabase = get_supabase_client()

    if not check_if_table_exists(supabase, table_name):
        message = missing_table_message(table_name)
        if logger:
            logger.error(message)
        raise RuntimeError(message)

    supabase.table(table_name).delete().neq("id", 0).execute()
    if logger:
        logger.info("Cleared existing rows from '%s'.", table_name)

    insert_current_team(df, table_name=table_name, logger=logger, supabase=supabase)


def insert_current_team(
    df: pd.DataFrame,
    table_name: str = DEFAULT_CURRENT_TEAM_TABLE,
    logger=None,
    supabase=None,
) -> None:
    """
    Insert current-team rows without clearing existing table contents.
    """
    validate_current_team_payload(df)
    supabase = supabase or get_supabase_client()

    if not check_if_table_exists(supabase, table_name):
        message = missing_table_message(table_name)
        if logger:
            logger.error(message)
        raise RuntimeError(message)

    rows = df.astype(object).where(pd.notna(df), None).to_dict(orient="records")
    insert_rows_into_table(supabase, table_name=table_name, rows=rows)
    if logger:
        logger.info("Inserted %s rows into '%s'.", len(rows), table_name)
