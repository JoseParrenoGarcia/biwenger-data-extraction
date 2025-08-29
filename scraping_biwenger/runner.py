from scraping_biwenger.get_current_team import ETL_get_current_team
from scraping_biwenger.get_player_stats import ETL_get_player_stats
from config_logging import get_logger
import time

def run_full_scraping_pipeline(test: bool = False):
    logger = get_logger("scraping_biwenger_logger", log_file="logs/runner_scraping_biwenger.log")
    start_time = time.time()

    logger.info("=" * 60)
    logger.info("🚀 STARTING FULL SCRAPING + ENRICHMENT PIPELINE")
    logger.info("=" * 60)

    # Step 1: Extract current team stats from Biwenger
    logger.info("🔍 Running ETL_get_current_team()...")
    step1_start = time.time()
    ETL_get_current_team()
    step1_duration = (time.time() - step1_start) / 60
    logger.info(f"✅ ETL_get_current_team completed in {step1_duration:.2f} minutes")

    # Step 2: Extract player stats
    logger.info("🔍 Running ETL_get_player_stats()...")
    step1_start = time.time()
    ETL_get_player_stats()
    step1_duration = (time.time() - step1_start) / 60
    logger.info(f"✅ ETL_get_player_stats completed in {step1_duration:.2f} minutes")

    total_duration = (time.time() - start_time) / 60
    logger.info("=" * 60)
    logger.info(f"✅ FULL PIPELINE COMPLETED SUCCESSFULLY in {total_duration:.2f} minutes")
    logger.info("=" * 60)


if __name__ == "__main__":
    run_full_scraping_pipeline()
