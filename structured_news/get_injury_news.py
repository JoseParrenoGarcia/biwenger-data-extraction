from config_logging import get_logger
from supabase_client.connection import get_supabase_client
from structured_news.utils import get_unique_teams

def ETL_get_injury_new():
    logger = get_logger("ETL_get_injury_new", log_file="logs/ETL_get_injury_new.log")
    logger.info("🚀 Starting ETL pipeline for ETL_get_injury_new...")

    supabase = get_supabase_client()

    logger.info("=" * 60)
    logger.info("READING SUPABASE TABLE AND EXTRACTING UNIQUE TEAMS")
    logger.info("=" * 60)
    teams = get_unique_teams("article_urls", logger)

    logger.info(f"Processing {len(teams)} teams: {teams}")
    for team in teams:
        logger.info(f"--- Handling injuries for team: {team} ---")


    # logger.info("=" * 60)
    # logger.info("READING SUPABASE TABLE AND FILTERING SPECIFIC ARTICLES")
    # logger.info("=" * 60)
    # articles = get_relevant_articles(supabase, logger)


if __name__ == "__main__":
    ETL_get_injury_new()