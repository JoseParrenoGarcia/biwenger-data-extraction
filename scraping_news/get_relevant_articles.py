from scraping_news.config_landing_pages import TEAM_NEWS_SOURCES_test, TEAM_NEWS_SOURCES
from scraping_news.scraper_utils import Website
from scraping_news.llm_prompts import prompt_url_relevance_filter
from llm_client.llm_orchestrator import call_llm
from config_logging import get_logger
from supabase_client.connection import get_supabase_client
from supabase_client.utils import check_if_table_exists

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
    logger.info("✅ Output structure validated. ")

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

            logger.info(f"✅ Filtered {team}: {sum(len(v) for v in parsed_team_result.values())} links retained.")

        except Exception as parse_err:
            logger.error(f"❌ Failed to parse or validate LLM output for {team}: {parse_err}")
            filtered_dict[team] = team_links_dict  # fallback

    return filtered_dict

def ETL_get_relevant_articles(test=False) -> dict:
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

    # Step 3: Check if Supabase table exists
    supabase = get_supabase_client()

    if not check_if_table_exists(supabase, "articles"):
        logger.warning("🛠 Table 'articles' does not exist. Creating it now...")
    else:
        logger.info("✅ Table 'articles' found.")

    # More steps: (future) Store in Supabase or log separately
    # 3. check if a database exists
    # 4. if not, we can store the links to the database (we could make it either as a text file database or a tabular set with features such as team, source, url)
    # 5. if it does, then we can extract the links from the database and compare them with the LLM output, we can filter out duplicates that we already have in the database.
    # 6. finally, append to the database new links.
    # 1. Check the links for duplicates (ie, look the current links vs the database one, only keep new ones)
    # 2. If database is empty them store directly. If not, then filter again for duplicates.
    # 3. Store the filtered links in Supabase or another storage solution

    # Step xxx: (future) Store in Supabase or log separately


    logger.info("=" * 60)
    logger.info("✅ ETL pipeline completed successfully.")
    return filtered_links_dict


if __name__ == "__main__":
    results = ETL_get_relevant_articles(test=True)
    print("\n🧠 Final output:")
    print(results)

