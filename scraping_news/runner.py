from scraping_news.get_relevant_articles import ETL_get_relevant_articles
from scraping_news.get_article_contents import ETL_get_article_contents
from config_logging import get_logger

def run_full_scraping_pipeline(test: bool = False):
    logger = get_logger("scraping_news_runner", log_file="logs/runner_scraping_news.log")

    logger.info("=" * 60)
    logger.info("🚀 STARTING FULL SCRAPING + ENRICHMENT PIPELINE")
    logger.info("=" * 60)

    # Step 1: Run URL collection and filtering
    logger.info("🔍 Running ETL_get_relevant_articles()...")
    ETL_get_relevant_articles(test=test)

    # Step 2: Run article scraping and LLM enrichment
    logger.info("🧠 Running ETL_get_article_contents()...")
    ETL_get_article_contents(test=test)

    logger.info("=" * 60)
    logger.info("✅ FULL PIPELINE COMPLETED SUCCESSFULLY")
    logger.info("=" * 60)


if __name__ == "__main__":
    run_full_scraping_pipeline(test=True)
