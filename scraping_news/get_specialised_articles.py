from scraping_news.config_landing_pages import MATCH_PREVIEW
from scraping_news.scraper_utils import Website
from scraping_news.utils import extract_code_block
from supabase_client.connection import get_supabase_client
from supabase_client.utils import check_if_table_exists, insert_rows_into_table
from config_logging import get_logger

import logging
from typing import List, Dict


def scrape_match_preview_links(logger: logging.Logger) -> List[str]:
    """
    Scrape match preview links from all known deterministic sources (e.g. JornadaPerfecta).

    Returns:
        List of fully constructed URLs (e.g. /partido/.../previa)
    """
    base_urls = MATCH_PREVIEW.get("ALL_TEAMS", [])
    all_preview_links = []

    for base_url in base_urls:
        logger.info(f"Scraping base match listing: {base_url}")

        try:
            website = Website(base_url)
            partido_links = website.get_links(include_substring="/partido/")

            # Append /previa to each unique link
            unique_previa_links = {link.rstrip("/") + "/previa" for link in partido_links}
            all_preview_links.extend(unique_previa_links)

            logger.info(f"➕Found {len(unique_previa_links)} preview links.")
            logger.info(f"{unique_previa_links}")
        except Exception as e:
            logger.error(f"❌ Failed to scrape {base_url}: {e}")

    return list(all_preview_links)

def insert_previews_as_articles(
    links: List[str],
    table_name: str,
    logger: logging.Logger
):
    """
    Insert scraped preview links into the article_urls table under ALL_TEAMS category.
    """
    supabase = get_supabase_client()

    if not check_if_table_exists(supabase, table_name):
        logger.warning(f"⚠️ Table '{table_name}' does not exist.")
        return

    logger.info("Fetching existing article URLs to deduplicate...")

    try:
        response = supabase.table(table_name).select("team, url").execute()
    except Exception as e:
        logger.error(f"❌ Failed to fetch from '{table_name}': {e}")
        return

    existing = {(row["team"], row["url"]) for row in response.data} if response.data else set()

    new_rows = [
        {"team": "Todos", "source": "www.jornadaperfecta.com", "url": url}
        for url in links
        if ("ALL_TEAMS", url) not in existing
    ]

    if not new_rows:
        logger.info("📭 No new preview links to insert.")
        return

    try:
        insert_rows_into_table(supabase, table_name=table_name, rows=new_rows)
        logger.info(f"✅ Inserted {len(new_rows)} preview links into '{table_name}'")
    except Exception as e:
        logger.error(f"❌ Failed to insert preview links: {e}")


def ETL_get_specialised_articles(test: bool = False):
    logger = get_logger("ETL_get_specialised_articles", log_file="logs/ETL_get_specialised_articles.log")
    logger.info("🚀 Starting specialised preview article extraction pipeline")

    preview_links = scrape_match_preview_links(logger)
    logger.info(f"🔎 Scraped total of {len(preview_links)} match preview links")

    insert_previews_as_articles(
        links=preview_links,
        table_name="article_urls",
        logger=logger
    )

    logger.info("✅ Specialised article ETL completed")


if __name__ == "__main__":
    ETL_get_specialised_articles(test=False)
