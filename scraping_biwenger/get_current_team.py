import argparse

import pandas as pd

from scraping_biwenger.current_team.persist import insert_current_team
from scraping_biwenger.current_team.pipeline import run_current_team_pipeline
from scraping_biwenger.current_team.scrape import (
    _mv_change_from_increment,
    _status_from_element,
    _to_float_generic,
    _to_int_generic,
    _to_int_money,
    scrape_basic_team_table,
)


def ETL_get_current_team(headless: bool = True, persist: bool = True):
    """
    Backward-compatible entry point for the current-team ETL.
    """
    return run_current_team_pipeline(headless=headless, persist=persist)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Biwenger current-team pipeline.")
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Show Chromium while scraping.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scrape and transform current-team rows without uploading to Supabase.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", None)
    pd.set_option("display.max_colwidth", None)

    args = parse_args()
    team_data = ETL_get_current_team(headless=not args.headed, persist=not args.dry_run)
    if args.dry_run:
        print("\nDRY RUN ONLY: no Supabase rows were written.")
        print(team_data.to_string(index=False))
