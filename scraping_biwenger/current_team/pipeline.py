from config_logging import get_logger
from scraping_biwenger.current_team.persist import DEFAULT_CURRENT_TEAM_TABLE, replace_current_team
from scraping_biwenger.current_team.scrape import scrape_basic_team_table
from scraping_biwenger.current_team.transform import transform_current_team
from scraping_biwenger.shared.auth import dismiss_app_popups_if_present, perform_login
from scraping_biwenger.shared.browser_session import start_browser_accept_cookies
from scraping_biwenger.shared.config import (
    CURRENT_TEAM_PROFILE,
    assert_biwenger_profile_allowed,
    load_biwenger_credentials,
)
from scraping_biwenger.shared.navigation import click_tab_in_horizontal_main_menu, scroll_into_view


def select_table_layout(page, logger=None) -> None:
    """
    Select the squad table layout when the page is not already rendering a table.
    """
    if page.locator("table.table.no-swipe tbody tr").first.count() > 0:
        if logger:
            logger.info("Current-team table is already visible.")
        return

    selectors = [
        '[role="button"][aria-label="Table"]',
        '[role="button"][title="Table"]',
        'button:has-text("Table")',
    ]
    for selector in selectors:
        try:
            page.locator(selector).first.click(timeout=3000)
            if logger:
                logger.info("Selected table layout with selector %s.", selector)
            return
        except Exception:
            if logger:
                logger.info("Table layout selector did not match: %s", selector)

    if logger:
        logger.info("No table layout selector matched; scraper will wait for table rows.")


def scrape_current_team_snapshot(page, logger=None):
    """
    Navigate from the logged-in app to the team table and return normalized rows.
    """
    click_tab_in_horizontal_main_menu(page, "team", logger=logger)
    dismiss_app_popups_if_present(page, logger=logger)
    select_table_layout(page, logger=logger)
    scroll_into_view(page, "segmented-control button[aria-label='Squad']")
    raw_df = scrape_basic_team_table(page)
    return transform_current_team(raw_df)


def run_current_team_pipeline(
    *,
    headless: bool = True,
    persist: bool = True,
    table_name: str = DEFAULT_CURRENT_TEAM_TABLE,
    logger=None,
):
    """
    Login to Biwenger, scrape the current-team table, and optionally persist it.
    """
    logger = logger or get_logger(
        "ETL_get_current_team",
        log_file="logs/ETL_get_current_team.log",
    )
    logger.info("=" * 70)
    logger.info("Starting ETL: get_current_team")
    logger.info("=" * 70)

    assert_biwenger_profile_allowed(use_case="current_team", profile=CURRENT_TEAM_PROFILE)
    creds = load_biwenger_credentials(profile=CURRENT_TEAM_PROFILE)
    logger.info("Credentials loaded successfully for profile '%s'.", CURRENT_TEAM_PROFILE)

    pw, browser, context, page = start_browser_accept_cookies(
        headless=headless,
        logger=logger,
    )
    logger.info("Browser session started.")

    try:
        perform_login(page, creds["email"], creds["password"], logger=logger)
        team_data = scrape_current_team_snapshot(page, logger=logger)
        logger.info("Scraped and transformed %s current-team rows.", len(team_data))

        if persist:
            replace_current_team(team_data, table_name=table_name, logger=logger)
        else:
            logger.info("Skipping Supabase persistence for current-team dry run.")

        return team_data
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
