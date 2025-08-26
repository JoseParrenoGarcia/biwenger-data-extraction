import time

from config_logging import get_logger
from scraping_biwenger.scraper_actions_in_biwenger import (
    load_biwenger_credentials,
    start_browser_accept_cookies,
    perform_login
)


def ETL_get_current_team():
    """
    ETL: Login to Biwenger, scrape current team stats, and (later) upload to Supabase.
    For now, this sets up logging and loads credentials.
    """
    logger = get_logger(
        "ETL_get_current_team",
        log_file="logs/ETL_get_current_team.log"
    )
    logger.info("=" * 70)
    logger.info("🚀 Starting ETL: get_current_team")
    logger.info("=" * 70)

    # 1) Load credentials (from secrets/biwenger.toml)
    creds = load_biwenger_credentials()
    logger.info("✅ Credentials loaded successfully.")

    # 2) Start browser
    pw, browser, context, page = start_browser_accept_cookies(headless=False)
    logger.info("✅ Logged in")

    # 3) Login
    perform_login(page, creds["email"], creds["password"])

    page.pause()

    # 2) [Next steps – placeholders for now]
    # session = start_browser()                # e.g., Selenium/Playwright
    # biwenger_login(session, creds)           # use creds safely
    # team_df = scrape_current_team(session)   # return parsed DataFrame or dict
    # upload_team_to_supabase(team_df)         # write to DB (dedup, etc.)


if __name__ == "__main__":
    ETL_get_current_team()