import argparse

import pandas as pd

from config_logging import get_logger
from scraping_biwenger.current_team.pipeline import scrape_current_team_snapshot
from scraping_biwenger.players.pipeline import scrape_players_snapshot
from scraping_biwenger.shared.auth import perform_login
from scraping_biwenger.shared.browser_session import start_browser_accept_cookies
from scraping_biwenger.shared.config import load_biwenger_credentials


def _print_df(title: str, df: pd.DataFrame, max_rows: int | None = None) -> None:
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)
    print(f"Rows: {len(df)}")
    print(f"Columns: {list(df.columns)}")

    if df.empty:
        print("(empty)")
        return

    rows_to_print = len(df) if max_rows is None else max_rows
    print(df.head(rows_to_print).to_string(index=False))


def verify_current_team(headless: bool) -> pd.DataFrame:
    logger = get_logger(
        "dev_verify_current_team",
        log_file="logs/dev_verify_biwenger.log",
    )
    creds = load_biwenger_credentials(profile="biwenger")
    pw, browser, context, page = start_browser_accept_cookies(
        headless=headless,
        logger=logger,
    )

    try:
        perform_login(page, creds["email"], creds["password"], logger=logger)
        df = scrape_current_team_snapshot(page, logger=logger)
        logger.info("Current-team dry run scraped %s rows.", len(df))
        return df
    finally:
        context.close()
        browser.close()
        pw.stop()


def verify_players(
    headless: bool,
    max_pages: int,
    max_players: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    logger = get_logger(
        "dev_verify_players",
        log_file="logs/dev_verify_biwenger.log",
    )
    creds = load_biwenger_credentials(profile="biwenger_player_scraper")
    pw, browser, context, page = start_browser_accept_cookies(
        headless=headless,
        logger=logger,
    )

    try:
        perform_login(page, creds["email"], creds["password"], logger=logger)
        return scrape_players_snapshot(
            page,
            logger,
            max_pages=max_pages,
            max_players_detail=max_players,
        )
    finally:
        context.close()
        browser.close()
        pw.stop()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=("Dry-run Biwenger scraping without writing to Supabase. Use this as a refactor smoke test.")
    )
    parser.add_argument(
        "--max-players",
        type=int,
        default=2,
        help="Number of players to scrape in the player dry run.",
    )
    parser.add_argument(
        "--max-player-pages",
        type=int,
        default=1,
        help="Number of player list pages to discover before limiting players.",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Show the browser while scraping.",
    )
    parser.add_argument(
        "--skip-current-team",
        action="store_true",
        help="Skip current-team dry run.",
    )
    parser.add_argument(
        "--skip-players",
        action="store_true",
        help="Skip player dry run.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    headless = not args.headed

    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 180)
    pd.set_option("display.max_colwidth", 80)

    print("DRY RUN ONLY: no Supabase client is created and no rows are written.")

    if not args.skip_current_team:
        current_team_df = verify_current_team(headless=headless)
        _print_df("Current Team - All Scraped Rows", current_team_df)

    if not args.skip_players:
        stats_df, matches_df, value_history_df = verify_players(
            headless=headless,
            max_pages=args.max_player_pages,
            max_players=args.max_players,
        )
        _print_df("Player Stats - Dry Run Sample", stats_df, max_rows=args.max_players)
        _print_df("Player Matches - Dry Run Sample", matches_df, max_rows=20)
        _print_df("Player Value History - Dry Run Sample", value_history_df, max_rows=20)

    print("\nDry run complete. Supabase writes were intentionally skipped.")


if __name__ == "__main__":
    main()
