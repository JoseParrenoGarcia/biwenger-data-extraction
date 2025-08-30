import logging
from supabase_client.connection import get_supabase_client
from supabase_client.utils import check_if_table_exists


MODULE_PROFILES = {
    "lesiones": {"tags": ["lesiones_sanciones"], "days": 14},
    "cronica_partido": {"tags": ["cronica_partido"], "days": 14},
    "transfers": {"tags": ["fichajes","renovaciones"], "days": 30},
    "previa_siguiente_partido": {"tags": ["previa_siguiente_partido"], "days": 7},
    "rueda_prensa": {"tags": ["rueda_prensa"], "days": 7},
}


def get_unique_teams(table_name: str, logger: logging.Logger) -> set:
    """
    Fetches the unique set of teams from the specified Supabase table.

    Args:
        table_name (str): Name of the table (e.g., 'article_urls').
        logger (Logger): Logger instance.

    Returns:
        Set of team names (strings).
    """
    supabase = get_supabase_client()

    if not check_if_table_exists(supabase, table_name):
        logger.warning(f"⚠️ Table '{table_name}' does not exist.")
        return set()

    try:
        response = supabase.table(table_name).select("team").execute()
        if not response.data:
            logger.info(f"Table '{table_name}' is empty or has no 'team' data.")
            return set()

        teams = {row["team"] for row in response.data if row.get("team")}
        logger.info(f"✅ Retrieved {len(teams)} unique teams from '{table_name}'")
        return teams

    except Exception as e:
        logger.error(f"❌ Failed to fetch unique teams from '{table_name}': {e}")
        return set()
