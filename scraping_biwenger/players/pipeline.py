from config_logging import get_logger
from scraping_biwenger.players.persist import persist_player_outputs
from scraping_biwenger.players.scrape import scrape_player_rows
from scraping_biwenger.players.transform import transform_player_outputs
from scraping_biwenger.scraper_actions_in_biwenger import (
    load_biwenger_credentials,
    perform_login,
    start_browser_accept_cookies,
)


def scrape_players_snapshot(
    page,
    logger,
    *,
    max_pages: int | None = None,
    max_players_detail: int | None = None,
    player_slug: str | None = None,
):
    """
    Scrape and normalize player stats, matches, and value history from a logged-in page.
    """
    players_list, player_detail_rows, match_rows, value_history_rows = scrape_player_rows(
        page,
        logger,
        max_pages=max_pages,
        max_players_detail=max_players_detail,
        player_slug=player_slug,
    )
    if not players_list:
        logger.warning("No players extracted; returning empty player payloads.")

    stats_df, matches_df, value_history_df = transform_player_outputs(
        player_detail_rows,
        match_rows,
        value_history_rows,
    )
    logger.info(
        "Transformed player payloads: %s stats rows, %s match rows, %s value rows.",
        len(stats_df),
        len(matches_df),
        len(value_history_df),
    )
    return stats_df, matches_df, value_history_df


def run_player_pipeline(
    *,
    headless: bool = True,
    persist: bool = True,
    max_pages: int = 100,
    max_players_detail: int = 1_000,
    player_slug: str | None = None,
    logger=None,
):
    """
    Login to Biwenger, scrape player data, and optionally persist it.
    """
    logger = logger or get_logger(
        "ETL_get_player_stats",
        log_file="logs/ETL_get_player_stats.log",
    )
    logger.info("=" * 70)
    logger.info("Starting ETL: get_player_stats")
    logger.info("=" * 70)

    creds = load_biwenger_credentials(profile="biwenger_player_scraper")
    logger.info("Credentials loaded successfully for profile 'biwenger_player_scraper'.")

    pw, browser, context, page = start_browser_accept_cookies(
        headless=headless,
        logger=logger,
    )
    logger.info("Browser session started.")

    try:
        perform_login(page, creds["email"], creds["password"], logger=logger)
        stats_df, matches_df, value_history_df = scrape_players_snapshot(
            page,
            logger,
            max_pages=max_pages,
            max_players_detail=max_players_detail,
            player_slug=player_slug,
        )

        if persist:
            persist_player_outputs(
                stats_df,
                matches_df,
                value_history_df,
                logger=logger,
            )
        else:
            logger.info("Skipping Supabase persistence for player dry run.")

        return stats_df, matches_df, value_history_df
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
