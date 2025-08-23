from supabase_client.connection import get_supabase_client
from supabase_client.utils import check_if_table_exists
from config_logging import get_logger

from typing import List, Dict
import logging
from scraper_utils import Website

def get_existing_article_ids(table_name: str, logger: logging.Logger) -> set:
    """
    Fetches existing article_id values from the article_contents table.

    Args:
        table_name (str): Name of the enriched content table.
        logger (Logger): Logger instance.

    Returns:
        Set of UUIDs corresponding to already scraped articles.
    """
    supabase = get_supabase_client()

    if not check_if_table_exists(supabase, table_name):
        logger.warning(f"⚠️ Table '{table_name}' does not exist.")
        return set()

    try:
        response = supabase.table(table_name).select("article_id").execute()
        article_ids = {row["article_id"] for row in response.data} if response.data else set()
        logger.info(f"Retrieved {len(article_ids)} existing article_ids from '{table_name}'")
        return article_ids
    except Exception as e:
        logger.error(f"❌ Failed to fetch from '{table_name}': {e}")
        return set()

def get_urls_to_scrape(logger: logging.Logger) -> List[Dict[str, str]]:
    """
    Fetches all article URLs from article_urls, then filters out those already in article_contents.

    Returns:
        List[Dict[str, str]]: Each dict has at least `id`, `url`, `team`, and `source`.
    """
    # Log the start of the operation with key parameters
    logger.info("=" * 60)
    logger.info("COLLECTING URLS TO SCRAPE THEIR CONTENTS")
    logger.info("=" * 60)

    supabase = get_supabase_client()

    try:
        url_response = supabase.table("article_urls").select("id, url, team, source").execute()
        all_articles = url_response.data if url_response.data else []
        logger.info(f"Retrieved {len(all_articles)} total articles from article_urls.")
    except Exception as e:
        logger.error(f"❌ Failed to fetch from 'article_urls': {e}")
        return []

    existing_article_ids = get_existing_article_ids("article_contents", logger)

    # Filter out articles already scraped
    articles_to_scrape = [row for row in all_articles if row["id"] not in existing_article_ids]
    logger.info(f"🆕 {len(articles_to_scrape)} articles still need to be scraped.")
    return articles_to_scrape

def scrape_and_build_article_content_row(article: dict, logger: logging.Logger) -> dict | None:
    """
    Scrapes an article URL and returns a row ready for insertion into article_contents.

    Args:
        article (dict): A row from article_urls with keys: id, url, team, source
        logger (Logger): Logger instance

    Returns:
        dict or None: Row dict with scraped data or None if scrape failed
    """
    url = article["url"]
    article_id = article["id"]

    try:
        website = Website(url)
        raw_text = website.text
        title = website.title
        published_date = website.published_at

        if not raw_text.strip():
            logger.warning(f"⚠️ Skipping {url} — empty text scraped.")
            return None

        return {
            "article_id": article_id,
            "url_text": url,
            "raw_text": raw_text,
            "title": title,
            "published_date": published_date,
        }

    except Exception as e:
        logger.error(f"❌ Failed to scrape {url}: {e}")
        return None

def ETL_get_article_contents(test: bool = False):
    """
    Orchestrates the scraping of full article contents from URLs already marked as relevant.

    1. Reads from article_urls
    2. Checks what's already in article_contents
    3. Returns list of URLs pending scraping
    """
    logger = get_logger("ETL_get_article_contents", log_file="logs/ETL_get_article_contents.log")
    logger.info("🚀 Starting ETL pipeline for article contents...")

    articles_to_scrape = get_urls_to_scrape(logger)

    if not articles_to_scrape:
        logger.info("✅ No new articles to scrape — pipeline complete.")
        return

    # # For now, just print the remaining URLs to scrape
    # for i, row in enumerate(articles_to_scrape, 1):
    #     print(f"{i}. [{row['team']}] {row['url']}")

    logger.info("Article scraping targets listed. Ready for content extraction stage.")

    logger.info("=" * 60)
    logger.info("SCRAPING ARTICLE CONTENTS")
    logger.info("=" * 60)
    rows_to_insert = []

    for i, article in enumerate(articles_to_scrape, 1):
        logger.info(f"🔁 ({i}/{len(articles_to_scrape)}) Processing: {article['url']}")
        row = scrape_and_build_article_content_row(article, logger)
        if row:
            rows_to_insert.append(row)

    return rows_to_insert


if __name__ == "__main__":
    rows_to_insert = ETL_get_article_contents(test=False)
    print(rows_to_insert)