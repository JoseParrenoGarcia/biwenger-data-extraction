import argparse

import pandas as pd

from config_logging import get_logger
from scraping_biwenger.current_team.pipeline import scrape_current_team_snapshot
from scraping_biwenger.helper_extract_all_player_names import extract_all_player_names
from scraping_biwenger.helper_pipeline_loop import scrape_all_players_detail
from scraping_biwenger.scraper_actions_in_biwenger import (
    click_tab_in_horizontal_main_menu,
    load_biwenger_credentials,
    perform_login,
    start_browser_accept_cookies,
)
from scraping_biwenger.utils import _rand_sleep


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


def _build_player_outputs(
    player_detail_rows: list[dict],
    match_rows: list[dict],
    value_history_rows: list[dict],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    today = pd.Timestamp.utcnow().date().isoformat()

    player_detail_df = (
        pd.DataFrame(player_detail_rows)
        .drop_duplicates(subset=["player_name"], keep="first")
        .drop(columns=["name", "slug", "href"], errors="ignore")
    )

    stats_df = player_detail_df.drop_duplicates(
        subset=["player_name", "team"],
        keep="last",
    )
    if not stats_df.empty:
        stats_df = stats_df.copy()
        stats_df["as_of_date"] = today

    matches_df = pd.DataFrame(match_rows)
    keep_cols = [
        "season_label",
        "round_label",
        "match_date",
        "points",
        "best_xi",
        "events",
        "player_name",
        "team",
    ]
    matches_df = matches_df[[c for c in keep_cols if c in matches_df.columns]].copy()
    if not matches_df.empty:
        matches_df["as_of_date"] = today
        matches_df = matches_df.drop_duplicates(
            subset=[
                "player_name",
                "team",
                "match_date",
                "season_label",
                "round_label",
                "points",
                "best_xi",
                "events",
            ],
            keep="last",
        )

    value_history_df = pd.DataFrame(value_history_rows)
    if not value_history_df.empty:
        value_history_df = value_history_df.copy()
        value_history_df["date"] = pd.to_datetime(
            value_history_df["date"],
            errors="coerce",
        ).dt.strftime("%Y-%m-%d")
        value_history_df["market_value_eur"] = pd.to_numeric(
            value_history_df["market_value_eur"],
            errors="coerce",
        )
        value_history_df = value_history_df.dropna(
            subset=["date", "market_value_eur"],
        )

    return stats_df, matches_df, value_history_df


def verify_current_team(headless: bool) -> pd.DataFrame:
    logger = get_logger(
        "dev_verify_current_team",
        log_file="logs/dev_verify_scraping.log",
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
        log_file="logs/dev_verify_scraping.log",
    )
    creds = load_biwenger_credentials(profile="biwenger_player_scraper")
    pw, browser, context, page = start_browser_accept_cookies(
        headless=headless,
        logger=logger,
    )

    try:
        perform_login(page, creds["email"], creds["password"], logger=logger)
        click_tab_in_horizontal_main_menu(page, "players", logger=logger)
        _rand_sleep(0.5, 1.5)
        page.get_by_role("button", name="Table").click()
        _rand_sleep(0.5, 1.5)

        players_list = extract_all_player_names(
            logger=logger,
            page=page,
            max_pages=max_pages,
        )
        players_list = players_list[:max_players]
        print(f"\nSelected {len(players_list)} players for dry run:")
        for player in players_list:
            print(f"- {player.get('name')} ({player.get('slug')})")

        player_detail_rows, match_rows, value_history_rows = scrape_all_players_detail(
            logger,
            page,
            players_list,
            max_players=max_players,
            collect_matches=True,
        )
        return _build_player_outputs(
            player_detail_rows,
            match_rows,
            value_history_rows,
        )
    finally:
        context.close()
        browser.close()
        pw.stop()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Dry-run Biwenger scraping without writing to Supabase. "
            "Use this as a refactor smoke test."
        )
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
