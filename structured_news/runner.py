from structured_news.get_injury_news import ETL_get_injury_news
from structured_news.get_transfer_news import ETL_get_transfer_news
from structured_news.get_next_match_news import ETL_get_next_match_news
from supabase_client.connection import get_supabase_client
from supabase_client.utils import check_if_table_exists, insert_rows_into_table


from config_logging import get_logger
import time

def run_full_scraping_pipeline():
    logger = get_logger("structured_news_runner", log_file="logs/structured_news_runner.log")
    start_time = time.time()

    logger.info("=" * 60)
    logger.info("🚀 STARTING ENRICHMENT PIPELINE")
    logger.info("=" * 60)

    supabase = get_supabase_client()
    table_name = "article_for_streamlit"

    if not check_if_table_exists(supabase, table_name):
        logger.error(f"❌ Table '{table_name}' does not exist in Supabase.")
    else:
        # Delete everything first (truncate semantics)
        supabase.table(table_name).delete().neq("id", 0).execute()
        logger.info(f"🗑️ Cleared existing rows from '{table_name}'")

    # Step 1
    logger.info("🔍 Running ETL_get_injury_news()...")
    step1_start = time.time()
    ETL_get_injury_news()
    step1_duration = (time.time() - step1_start) / 60
    logger.info(f"✅ ETL_get_injury_news completed in {step1_duration:.2f} minutes")

    # Step 2
    logger.info("🔍 Running ETL_get_transfer_news()...")
    step1_start = time.time()
    ETL_get_transfer_news()
    step1_duration = (time.time() - step1_start) / 60
    logger.info(f"✅ ETL_get_transfer_news completed in {step1_duration:.2f} minutes")

    # Step 3
    logger.info("🔍 Running ETL_get_next_match_news()...")
    step1_start = time.time()
    ETL_get_next_match_news()
    step1_duration = (time.time() - step1_start) / 60
    logger.info(f"✅ ETL_get_next_match_news completed in {step1_duration:.2f} minutes")

    total_duration = (time.time() - start_time) / 60
    logger.info("=" * 60)
    logger.info(f"✅ FULL PIPELINE COMPLETED SUCCESSFULLY in {total_duration:.2f} minutes")
    logger.info("=" * 60)


if __name__ == "__main__":
    # run_full_scraping_pipeline(test=True)
    run_full_scraping_pipeline()
