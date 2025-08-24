from scraping_news.get_relevant_articles import ETL_get_relevant_articles
from scraping_news.get_article_contents import ETL_get_article_contents
from config_logging import get_logger
import time

def run_full_scraping_pipeline(test: bool = False):
    logger = get_logger("scraping_news_runner", log_file="logs/runner_scraping_news.log")
    start_time = time.time()

    logger.info("=" * 60)
    logger.info("🚀 STARTING FULL SCRAPING + ENRICHMENT PIPELINE")
    logger.info("=" * 60)

    # Step 1: Run URL collection and filtering
    logger.info("🔍 Running ETL_get_relevant_articles()...")
    step1_start = time.time()
    ETL_get_relevant_articles(test=test)
    step1_duration = (time.time() - step1_start) / 60
    logger.info(f"✅ ETL_get_relevant_articles completed in {step1_duration:.2f} minutes")

    # Step 2: Run article scraping and LLM enrichment
    logger.info("🧠 Running ETL_get_article_contents()...")
    step2_start = time.time()
    ETL_get_article_contents(test=test)
    step2_duration = (time.time() - step2_start) / 60
    logger.info(f"✅ ETL_get_article_contents completed in {step2_duration:.2f} minutes")

    total_duration = (time.time() - start_time) / 60
    logger.info("=" * 60)
    logger.info(f"✅ FULL PIPELINE COMPLETED SUCCESSFULLY in {total_duration:.2f} minutes")
    logger.info("=" * 60)


if __name__ == "__main__":
    run_full_scraping_pipeline(test=True)
