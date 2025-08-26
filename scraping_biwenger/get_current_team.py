import time

from config_logging import get_logger
from scraping_biwenger.scraper_actions_in_biwenger import (
    load_biwenger_credentials,
    start_browser_accept_cookies,
    perform_login,
    click_tab_in_horizontal_main_menu
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

    # 4) Navigate to team page
    click_tab_in_horizontal_main_menu(page, "team")

    page.pause()




if __name__ == "__main__":
    ETL_get_current_team()