from config_logging import get_logger
from supabase_client.connection import get_supabase_client
from structured_news.utils import (
    get_unique_teams,
    get_recent_articles,
    filter_articles_by_team,
    filter_articles_by_tag,
    MODULE_PROFILES
)
import pandas as pd

def ETL_get_injury_new():
    logger = get_logger("ETL_get_injury_new", log_file="logs/ETL_get_injury_new.log")
    logger.info("🚀 Starting ETL pipeline for ETL_get_injury_new...")

    supabase = get_supabase_client()

    logger.info("=" * 60)
    logger.info("READING SUPABASE TABLE AND EXTRACTING UNIQUE TEAMS")
    logger.info("=" * 60)

    teams = list(get_unique_teams("article_urls", logger))
    injury_tags = MODULE_PROFILES["lesiones"]["tags"]  # ["lesiones_sanciones"]

    logger.info(f"Processing {len(teams)} teams: {teams}")
    for team in teams[:1]:
        logger.info(f"--- Handling injuries for team: {team} ---")

        # Pull once for the cutoff window
        all_articles_df = get_recent_articles("article_contents", days=14, logger=logger)
        if all_articles_df.empty:
            logger.info("No recent articles. Exiting.")
            return

        logger.info(f"--- Handling injuries for team: {team} ---")

        team_articles_df = filter_articles_by_team(all_articles_df, team)
        if team_articles_df.empty:
            logger.info(f"No articles for team {team}. Skipping.")
            continue

        injury_articles_df = filter_articles_by_tag(
            team_articles_df,
            tags=injury_tags,
            tags_col="tags_llm",  # change if your column name differs
            match="any",
            case_insensitive=True,
        )
        logger.info(f"Found {len(injury_articles_df)} injury-tagged articles for {team}")

        # print(injury_articles_df[['tags_llm', 'recognised_teams_llm']].head())
        # print(team_articles_df.dtypes)

    logger.info("=" * 60)
    logger.info("FORMATTING LLM OUTPUT FOR INJURY TABLE")
    logger.info("=" * 60)


if __name__ == "__main__":
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)
    pd.set_option('display.max_colwidth', None)

    ETL_get_injury_new()