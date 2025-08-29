from supabase_client.connection import get_supabase_client
from supabase_client.utils import check_if_table_exists, insert_rows_into_table
from llm_client.llm_orchestrator import call_llm
from scraping_news.llm_prompts import prompt_article_summary_and_tags
from scraping_news.utils import extract_code_block
from scraping_news.scraper_utils import Website
from config_logging import get_logger

from typing import List, Dict
import logging
import ast

from concurrent.futures import ThreadPoolExecutor, as_completed

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

def get_urls_to_scrape(supabase, logger: logging.Logger) -> List[Dict[str, str]]:
    """
    Fetches all article URLs from article_urls, then filters out those already in article_contents.

    Returns:
        List[Dict[str, str]]: Each dict has at least `id`, `url`, `team`, and `source`.
    """
    # Log the start of the operation with key parameters
    logger.info("=" * 60)
    logger.info("COLLECTING URLS TO SCRAPE THEIR CONTENTS")
    logger.info("=" * 60)

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
    url = article["url"]
    article_id = article["id"]

    logger.info(f"🌐 Scraping content from URL: {url}")

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
            "url": url,
            "published_date": published_date,
            "raw_text": raw_text,
            "title": title
        }

    except Exception as e:
        logger.error(f"❌ Failed to scrape {url}: {e}")
        return None

def enrich_row_with_llm(row: dict, logger: logging.Logger) -> dict | None:
    """
    Adds LLM-generated summary, tags, and named entities to a scraped article row.

    Args:
        row (dict): Must contain at least 'raw_text' and 'title'
        logger (Logger): Logger instance

    Returns:
        dict | None: Enriched row with LLM fields or None if failure
    """
    url = row.get("url", "unknown URL")
    logger.info(f"Summarising article via LLM: {url}")

    system_prompt, user_prompt = prompt_article_summary_and_tags(
        article_text=row["raw_text"],
        article_title=row.get("title", "")
    )

    llm_response = call_llm(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model_priority=["gemini", "openai"],
        logger=logger
    )

    try:
        clean_json_str = extract_code_block(llm_response)
        parsed_output = ast.literal_eval(clean_json_str)

        # Add LLM fields to the row
        row["summary_llm"] = parsed_output.get("summary")
        row["tags_llm"] = parsed_output.get("tags_llm", [])
        row["recognised_teams_llm"] = parsed_output.get("recognised_teams_llm", [])
        row["recognised_people_llm"] = parsed_output.get("recognised_people_llm", [])

        return row

    except Exception as e:
        logger.error(f"❌ Failed to parse or enrich article with LLM: {e}")
        return None

def ETL_get_article_contents(test: bool = False):
    """
    Orchestrates the scraping of full article contents from URLs already marked as relevant.
    Now includes parallel LLM enrichment using ThreadPoolExecutor.
    """
    logger = get_logger("ETL_get_article_contents", log_file="logs/ETL_get_article_contents.log")
    logger.info("🚀 Starting ETL pipeline for article contents...")

    supabase = get_supabase_client()
    articles_to_scrape = get_urls_to_scrape(supabase, logger)

    if not articles_to_scrape:
        logger.info("✅ No new articles to scrape — pipeline complete.")
        return
    else:
        print(f"📋 {len(articles_to_scrape)} articles")
        print(articles_to_scrape)

    logger.info(f"📋 {len(articles_to_scrape)} articles pending scraping.")
    logger.info("=" * 60)
    logger.info("SCRAPING ARTICLE CONTENTS")
    logger.info("=" * 60)

    scraped_rows = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_article = {
            executor.submit(scrape_and_build_article_content_row, article, logger): article
            for article in articles_to_scrape
        }

        for future in as_completed(future_to_article):
            result = future.result()
            if result:
                scraped_rows.append(result)

    if not scraped_rows:
        logger.info("⚠️ No valid articles were scraped. Exiting early.")
        return

    logger.info("=" * 60)
    logger.info("ENRICHING WITH LLM (5 threads in parallel)")
    logger.info("=" * 60)

    rows_to_insert = []

    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_row = {executor.submit(enrich_row_with_llm, row, logger): row for row in scraped_rows}

        for future in as_completed(future_to_row):
            result = future.result()
            if result:
                rows_to_insert.append(result)

    logger.info("=" * 60)
    logger.info("WRITING TO DATABASE")
    logger.info("=" * 60)

    if rows_to_insert:
        try:
            insert_rows_into_table(
                supabase=supabase,
                table_name="article_contents",
                rows=rows_to_insert
            )
            logger.info(f"✅ Successfully inserted {len(rows_to_insert)} enriched articles into 'article_contents'")
        except Exception as e:
            logger.error(f"❌ Failed to insert rows into 'article_contents': {e}")
    else:
        logger.info("📭 No articles were enriched or ready for insertion.")

if __name__ == "__main__":
    ETL_get_article_contents(test=True)