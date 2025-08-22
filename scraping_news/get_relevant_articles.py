from scraping_news.config_landing_pages import TEAM_NEWS_SOURCES_test, TEAM_NEWS_SOURCES
from scraping_news.scraper_utils import Website
from scraping_news.llm_prompts import prompt_url_relevance_filter
from llm_client.llm_orchestrator import call_llm
from config_logging import get_logger
from supabase_client.connection import get_supabase_client
from supabase_client.utils import check_if_table_exists, insert_rows_into_table

from typing import Dict, List
import logging
import re
import ast
from typing import Optional

def _validate_scraped_links_structure(data: dict) -> None:
    """
    Validates that the input dictionary follows the expected structure:
    {team: {source_url: [list_of_link_strings]}}

    Raises:
        AssertionError: If the structure does not match expectations.
    """
    assert isinstance(data, dict), "Input must be a dictionary"

    for team, sources in data.items():
        assert isinstance(sources, dict), f"Each team must map to a dict of sources. Found: {type(sources)}"
        for source_url, links in sources.items():
            assert isinstance(links, list), f"Each source URL must map to a list of links. Found: {type(links)}"
            for link in links:
                assert isinstance(link, str), f"Each link must be a string. Found: {type(link)}"

def _extract_code_block(text: str) -> str:
    """
    Extracts a JSON-like code block from an LLM response that may be wrapped in triple backticks or triple quotes.

    Supports:
    - ```json
    - ```python
    - ``` (no lang)
    - '''python
    - ''' (no lang)

    Args:
        text (str): Raw string from LLM

    Returns:
        str: Cleaned block, or original text if no match found
    """
    # Matches ```json\n{...}\n```, ```python\n{...}```, '''python\n{...}''', etc.
    match = re.search(r"(?:```|''')\s*(?:json|python)?\s*(\{.*?\})\s*(?:```|''')", text, re.DOTALL)
    return match.group(1).strip() if match else text.strip()

def scrape_landing_pages_for_url_extractions(
        test=False,
        verbose=False,
        logger: Optional[logging.Logger] = None
):
    """
    Scrape all websites from TEAM_NEWS_SOURCES and extract URLs found on each page.

    Args:
        test (bool): If True, use TEAM_NEWS_SOURCES_test, otherwise use TEAM_NEWS_SOURCES
        verbose (bool): If True, print all found URLs during scraping

    Returns:
        dict: Nested dictionary with structure:
              {team: {source_url: [list_of_unique_urls]}}
    """
    # Initialize logger for this module
    if logger is None:
        logger = logging.getLogger(__name__)

    # Choose which source dictionary to use
    TEAM_NEWS_SOURCES_to_use = TEAM_NEWS_SOURCES_test if test else TEAM_NEWS_SOURCES

    # Calculate total sources for progress tracking
    total_sources = sum(len(sources) for sources in TEAM_NEWS_SOURCES_to_use.values())
    total_teams = len(TEAM_NEWS_SOURCES_to_use)

    # Log the start of the operation with key parameters
    logger.info("=" * 60)
    logger.info("STARTING URL EXTRACTION PROCESS")
    logger.info(f"Scope: {total_teams} teams, {total_sources} total sources")
    logger.info("=" * 60)

    # Initialize the results dictionary
    results = {}

    for team_idx, (team, sources) in enumerate(TEAM_NEWS_SOURCES_to_use.items(), 1):
        logger.info("-" * 30)
        logger.info(f"Team {team_idx}/{total_teams}: {team}")
        logger.info("-" * 30)

        # Initialize team entry in results
        results[team] = {}

        for source_url in sources:
            logger.info(f"-> Scraping: {source_url}")

            try:
                # Create Website instance and scrape the page
                website = Website(source_url)

                # Get all links found on the page and deduplicate them
                links = website.get_links()
                unique_links = list(set(links))

                # Store results for this source
                results[team][source_url] = unique_links

                logger.info(f"--> Found {len(unique_links)} unique links (was {len(links)} before deduplication)")

                if verbose and unique_links:
                    for i, link in enumerate(unique_links, 1):
                        print(f"  {i}. {link}")
                elif verbose:
                    print("No links found on this page")

            except Exception as e:
                print(f"Error scraping {source_url}: {e}")
                # Store empty list for failed scrapes
                results[team][source_url] = []

    logger.info("-" * 30)
    logger.info("Ensuring output structure is valid...")
    _validate_scraped_links_structure(data=results)
    logger.info("Output structure validated. ")

    return results

def filter_links_with_llm(
    scraped_links_dict: Dict[str, Dict[str, List[str]]],
    model_priority: List[str] = ["gemini", "openai"],
    logger: Optional[logging.Logger] = None
) -> Dict[str, Dict[str, List[str]]]:
    """
    Filters article links using an LLM to determine relevance, preserving the original structure.

    Args:
        scraped_links_dict (dict): Dictionary in the format:
            {team: {source_url: [list_of_links]}}
        model_priority (List[str]): Ordered list of LLMs to try (e.g. ["gemini", "openai"])
        logger (logging.Logger): Optional logger instance.

    Returns:
        dict: Same structure as input, but with non-relevant links removed.
    """
    # Initialize logger for this module
    if logger is None:
        logger = logging.getLogger(__name__)

    # Log the start of the operation with key parameters
    logger.info("=" * 60)
    logger.info("STARTING URL FILTERING PROCESS")
    logger.info("=" * 60)

    # === Validate input structure ===
    logger.info("Ensuring input structure is valid...")
    _validate_scraped_links_structure(data=scraped_links_dict)

    # === Loop through teams to extract relevant articles with LLMs ===
    filtered_dict = {}

    for team, team_links_dict in scraped_links_dict.items():
        logger.info(f"LLM filtering for {team}...")
        system_prompt, user_prompt = prompt_url_relevance_filter(team=team, team_links_dict=team_links_dict)

        # Call LLM with fallback strategy
        llm_response = call_llm(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model_priority=model_priority,
            logger=logger,
        )

        if not llm_response:
            logger.warning(f"⚠️ No LLM response for team: {team}. Skipping filtering operation (keeping input dictionary as it was).")
            filtered_dict[team] = team_links_dict  # fallback: keep all
            continue

        # Extract the JSON-like code block from the response
        llm_response_clean = _extract_code_block(llm_response)

        try:
            parsed_team_result = ast.literal_eval(llm_response_clean)
            _validate_scraped_links_structure({team: parsed_team_result})

            # Assign it directly to the current team
            filtered_dict[team] = parsed_team_result

            logger.info(f"Filtered {team}: {sum(len(v) for v in parsed_team_result.values())} links retained.")

        except Exception as parse_err:
            logger.error(f"❌ Failed to parse or validate LLM output for {team}: {parse_err}")
            filtered_dict[team] = team_links_dict  # fallback

    return filtered_dict


def flatten_filtered_links_dict(
        filtered_links_dict: dict,
        logger: Optional[logging.Logger] = None
) -> list[dict]:
    """
    Converts a nested dictionary of the format:
    {team: {source_url: [list of urls]}}
    into a flat list of rows: [{team, source, url}].

    Args:
        filtered_links_dict (dict): Filtered article URLs

    Returns:
        List[dict]: Flat list of insertable rows
    """
    logger.info("=" * 60)
    logger.info("FLATTENING FILTERED LINKS DICTIONARY IN PREPARATION FOR STORAGE")
    logger.info("=" * 60)
    flattened = []

    for team, sources in filtered_links_dict.items():
        for source_url, urls in sources.items():
            for url in urls:
                flattened.append({
                    "team": team,
                    "source": source_url,
                    "url": url
                })

    return flattened

def insert_deduplicated_articles_in_database(
    flat_rows: List[Dict[str, str]],
    table_name: str,
    logger: logging.Logger
) -> None:
    """
    Inserts only non-duplicate article records into Supabase.

    Args:
        flat_rows (List[Dict]): Rows to insert (must have 'team' and 'url' keys)
        table_name (str): Name of the Supabase table to insert into
        logger (Logger): Logger instance for consistent tracking
    """
    logger.info("=" * 60)
    logger.info("STARTING STORAGE PROCESS TO SUPABASE")
    logger.info("=" * 60)

    supabase = get_supabase_client()

    if not check_if_table_exists(supabase, table_name):
        logger.warning(f"❌ Table '{table_name}' does not exist!")
        return

    logger.info(f"✅ Table '{table_name}' found.")
    logger.info("Fetching existing article URLs from Supabase to filter duplicates...")

    try:
        response = supabase.table(table_name).select("team, url").execute()
    except Exception as e:
        logger.error(f"❌ Failed to fetch existing data from '{table_name}': {e}")
        return

    # Extract existing (team, url) pairs into a set
    existing_team_url_set = {
        (row["team"], row["url"]) for row in response.data
    } if response.data else set()

    if existing_team_url_set:
        logger.info(f"Found {len(existing_team_url_set)} existing records.")
    else:
        logger.info("No existing records found — table is empty.")

    # Filter out rows already in the database
    new_rows_to_insert = [
        row for row in flat_rows
        if (row["team"], row["url"]) not in existing_team_url_set
    ]

    logger.info(f"Filtered out {len(flat_rows) - len(new_rows_to_insert)} duplicates.")
    logger.info(f"Ready to insert {len(new_rows_to_insert)} new articles.")

    # Insert only new rows
    if new_rows_to_insert:
        try:
            insert_rows_into_table(supabase, table_name=table_name, rows=new_rows_to_insert)
            logger.info(f"✅ Successfully inserted {len(new_rows_to_insert)} new rows into '{table_name}'")
        except Exception as e:
            logger.error(f"❌ Failed to insert into Supabase: {e}")
    else:
        logger.info("⏩ No new articles to insert — skipping write operation.")

def ETL_get_relevant_articles(test=False):
    """
    Orchestrates the full pipeline:
    1. Scrapes article URLs for each team from configured news sources.
    2. Filters those links for relevance using an LLM.
    3. (Future) Saves relevant links to Supabase or other storage.

    Returns:
        dict: Filtered dictionary {team: {source_url: [relevant_links]}}
    """
    logger = get_logger("ETL_get_relevant_articles", log_file="logs/ETL_get_relevant_articles.log")
    logger.info("🚀 Starting ETL pipeline for relevant articles...")

    # Step 1: Scrape landing pages
    scraped_links_dict = scrape_landing_pages_for_url_extractions(
        test=test,
        verbose=False,
        logger=logger
    )

    # Step 2: Filter with LLM
    filtered_links_dict = filter_links_with_llm(
        scraped_links_dict=scraped_links_dict,
        model_priority=["gemini", "openai"],
        logger=logger
    )

    # Step 3: Flatten the dictionary for easier storage
    flat_rows = flatten_filtered_links_dict(filtered_links_dict, logger)
    logger.info(f"Flattened filtered links into {flat_rows} rows for potential storage.")
    # flat_rows = [
    # {
    #     "team": "Valencia",
    #     "source": "https://www.superdeporte.es/valencia-cf/",
    #     "url": "https://www.superdeporte.es/valencia-cf/2025/08/20/yangel-herrera-clave-llegada-sadiq-valencia-cf-120801557.html"
    # },
    # {
    #     "team": "Valencia",
    #     "source": "https://plazadeportiva.valenciaplaza.com/valenciacf/",
    #     "url": "https://plazadeportiva.valenciaplaza.com/plazadeportiva/valenciacf/ron-gourlay-hay-muchas-vocesen-cuanto-a-la-posibilidad-de-incorporar-un-delantero-pero-veremos-como-va"
    # },
    # {
    #     "team": "Real Madrid",
    #     "source": "https://www.marca.com/futbol/real-madrid.html",
    #     "url": "https://www.marca.com/futbol/real-madrid/2025/08/20/mbappe-recupera-espiritu.html"
    # },
    # {
    #     "team": "Real Madrid",
    #     "source": "https://as.com/noticias/real-madrid/",
    #     "url": "https://as.com/futbol/mastantuono-esta-bendecido-n/"
    # },
    # {
    #     "team": "Real Madrid",
    #     "source": "https://as.com/noticias/real-madrid/",
    #     "url": "otra URL"
    # }
# ]

    insert_deduplicated_articles_in_database(
        flat_rows=flat_rows,
        table_name="article_urls",
        logger=logger
    )

    logger.info("=" * 60)
    logger.info("✅ ETL pipeline completed successfully.")


if __name__ == "__main__":
    ETL_get_relevant_articles(test=True)

