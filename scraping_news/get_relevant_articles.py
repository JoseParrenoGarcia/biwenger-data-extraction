from scraping_news.config_landing_pages import TEAM_NEWS_SOURCES_test, TEAM_NEWS_SOURCES
from scraping_news.scraper_utils import Website
from config_logging import get_logger


def scrape_landing_pages_for_url_extractions(
        test=False,
        verbose=False,
        log_file="logs/get_relevant_articles_scrape_landing_pages_for_url_extractions.log"
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
    logger = get_logger(__name__, log_file=log_file, include_timestamp_in_filename=True)

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

    return results

# Run the function
if __name__ == "__main__":
    extracted_urls = scrape_landing_pages_for_url_extractions(test=True)

    print(f"{'=' * 50}")
    print(extracted_urls)