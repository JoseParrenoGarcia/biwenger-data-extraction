import argparse

import pandas as pd

from scraping_biwenger.players.pipeline import run_player_pipeline


def ETL_get_player_stats(
    max_pages: int = 100,
    max_players_detail: int = 1_000,
    *,
    headless: bool = True,
    persist: bool = True,
):
    """
    Backward-compatible entry point for the player ETL.
    """
    return run_player_pipeline(
        headless=headless,
        persist=persist,
        max_pages=max_pages,
        max_players_detail=max_players_detail,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Biwenger player pipeline.")
    parser.add_argument(
        "command",
        nargs="?",
        choices=["run_scraping_players"],
        help="Legacy optional subcommand kept for scheduled scripts.",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Show Chromium while scraping.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scrape and transform player rows without uploading to Supabase.",
    )
    parser.add_argument(
        "--max-players",
        type=int,
        default=1_000,
        help="Maximum number of player detail pages to scrape.",
    )
    parser.add_argument(
        "--max-player-pages",
        type=int,
        default=100,
        help="Maximum number of player list pages to discover.",
    )
    return parser.parse_args()


def _print_df(title: str, df: pd.DataFrame, max_rows: int = 20) -> None:
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)
    print(f"Rows: {len(df)}")
    print(f"Columns: {list(df.columns)}")
    if df.empty:
        print("(empty)")
        return
    print(df.head(max_rows).to_string(index=False))


def main() -> None:
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", None)
    pd.set_option("display.max_colwidth", None)

    args = parse_args()
    stats_df, matches_df, value_history_df = ETL_get_player_stats(
        max_pages=args.max_player_pages,
        max_players_detail=args.max_players,
        headless=not args.headed,
        persist=not args.dry_run,
    )
    if args.dry_run:
        print("\nDRY RUN ONLY: no Supabase rows were written.")
        _print_df("Player Stats - Dry Run", stats_df, max_rows=args.max_players)
        _print_df("Player Matches - Dry Run", matches_df, max_rows=20)
        _print_df("Player Value History - Dry Run", value_history_df, max_rows=20)


if __name__ == "__main__":
    main()
