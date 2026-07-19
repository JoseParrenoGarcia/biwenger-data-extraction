import argparse
import time

from config_logging import get_logger
from scraping_biwenger.current_team.pipeline import run_current_team_pipeline
from scraping_biwenger.players.pipeline import run_player_pipeline


def run_full_scraping_pipeline() -> None:
    logger = get_logger("scraping_biwenger_logger", log_file="logs/runner_scraping_biwenger.log")
    start_time = time.time()

    logger.info("=" * 60)
    logger.info("STARTING FULL BIWENGER SCRAPING PIPELINE")
    logger.info("=" * 60)

    logger.info("Running current-team pipeline...")
    current_team_start = time.time()
    run_current_team_pipeline(logger=logger)
    current_team_duration = (time.time() - current_team_start) / 60
    logger.info("Current-team pipeline completed in %.2f minutes", current_team_duration)

    logger.info("Running player pipeline...")
    players_start = time.time()
    run_player_pipeline(logger=logger)
    players_duration = (time.time() - players_start) / 60
    logger.info("Player pipeline completed in %.2f minutes", players_duration)

    total_duration = (time.time() - start_time) / 60
    logger.info("=" * 60)
    logger.info("FULL BIWENGER SCRAPING PIPELINE COMPLETED SUCCESSFULLY in %.2f minutes", total_duration)
    logger.info("=" * 60)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the full Biwenger scraping pipeline.")
    parser.add_argument(
        "command",
        nargs="?",
        choices=["run_scraping_players"],
        help="Legacy optional subcommand kept for scheduled scripts.",
    )
    return parser.parse_args()


def main() -> None:
    parse_args()
    run_full_scraping_pipeline()


if __name__ == "__main__":
    main()
