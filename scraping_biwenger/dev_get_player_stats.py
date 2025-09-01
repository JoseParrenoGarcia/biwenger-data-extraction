from config_logging import get_logger
from scraping_biwenger.scraper_actions_in_biwenger import (
    load_biwenger_credentials,
    start_browser_accept_cookies,
    perform_login,
    click_tab_in_horizontal_main_menu,
)
from scraping_biwenger.helper_extract_all_player_names import extract_all_player_names
from scraping_biwenger.helper_search_and_open_player import open_player_via_search
from scraping_biwenger.helper_pipeline_loop import scrape_all_players_detail
from scraping_biwenger.utils import _rand_sleep
import time
import random

# ----------------------------------------------------------------------



# ----------------------------------------------------------------------


def ETL_get_player_stats(max_pages=100, max_players_detail=1_000):
    """
    ETL: Login to Biwenger, scrape player stats, and (later) upload to Supabase.
    """
    logger = get_logger(
        "ETL_get_player_stats",
        log_file="logs/ETL_get_player_stats.log"
    )
    logger.info("=" * 70)
    logger.info("🚀 Starting ETL: get_player_stats")
    logger.info("=" * 70)

    # 1) Load credentials (from secrets/biwenger.toml)
    creds = load_biwenger_credentials(profile="biwenger_player_scraper")
    logger.info("✅ Credentials loaded successfully.")

    # 2) Start browser
    pw, browser, context, page = start_browser_accept_cookies(headless=False)
    logger.info("✅ Logged in")

    # 3) Login
    try:
        perform_login(page, creds["email"], creds["password"])

        # 4) Navigate to players page
        click_tab_in_horizontal_main_menu(page, "players")
        _rand_sleep(0.5, 1.5)

        # 5) Click view as list
        page.get_by_role("button", name="Table").click()
        _rand_sleep(0.5, 1.5)

        # 6) Extract all player names
        players_list = extract_all_player_names(logger=logger, page=page, max_pages=max_pages)
        print(players_list)

        if not players_list:
            logger.warning("No players extracted; aborting search step.")
            return

        # 7) Extract details for each player via search + open + scrape + back
        detail_rows = scrape_all_players_detail(
            logger, page, players_list, max_players=max_players_detail
        )

        print(detail_rows)

        page.pause()


    finally:
        try:
            context.close()
        except Exception:
            pass
        try:
            browser.close()
        except Exception:
            pass
        try:
            pw.stop()
        except Exception:
            pass

if __name__ == "__main__":
    ETL_get_player_stats(max_pages=2)
