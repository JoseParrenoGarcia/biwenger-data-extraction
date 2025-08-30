import logging
from supabase_client.connection import get_supabase_client
from supabase_client.utils import check_if_table_exists
import pandas as pd
from datetime import datetime, timedelta

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

def get_recent_articles(table_name: str, days: int, logger: logging.Logger) -> pd.DataFrame:
    """
    Fetches articles from the specified Supabase table within the last `days`.

    Args:
        table_name (str): Name of the table (e.g., 'article_contents').
        days (int): Number of days back from today to include.
        logger (Logger): Logger instance.

    Returns:
        pd.DataFrame: DataFrame containing recent articles, empty if none found.
    """
    supabase = get_supabase_client()

    if not check_if_table_exists(supabase, table_name):
        logger.warning(f"⚠️ Table '{table_name}' does not exist.")
        return pd.DataFrame()

    # Compute cutoff datetime in ISO format
    cutoff_date = (datetime.today() - timedelta(days=days)).isoformat()

    try:
        # Query Supabase for rows newer than cutoff
        response = (
            supabase.table(table_name)
            .select("*")
            .gte("published_date", cutoff_date)
            .execute()
        )

        if not response.data:
            logger.info(f"No articles found in '{table_name}' within the last {days} days.")
            return pd.DataFrame()

        df = pd.DataFrame(response.data)
        logger.info(f"✅ Retrieved {len(df)} articles from '{table_name}' (last {days} days).")
        return df

    except Exception as e:
        logger.error(f"❌ Failed to fetch recent articles from '{table_name}': {e}")
        return pd.DataFrame()