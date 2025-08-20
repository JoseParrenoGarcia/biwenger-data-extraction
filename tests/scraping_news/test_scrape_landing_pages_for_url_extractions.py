from unittest.mock import patch
from scraping_news.get_relevant_articles import scrape_landing_pages_for_url_extractions

# Fake config to control test inputs
FAKE_TEAM_SOURCES = {
    "Valencia": ["https://example.com/valencia"],
    "Betis": ["https://example.com/betis"]
}


@patch("scraping_news.get_relevant_articles.Website")
@patch("scraping_news.get_relevant_articles.TEAM_NEWS_SOURCES_test", FAKE_TEAM_SOURCES)
def test_returns_dict_structure(mock_website):
    """
    Test that the function returns a properly structured dictionary:
    - Top-level keys should match team names.
    - Second-level keys should be source URLs.
    - The final values should be lists of string URLs.

    The Website class and the config are patched so no real HTTP requests or live configs are used.
    """

    # Mock the output of Website.get_links() so we have full control
    mock_website.return_value.get_links.return_value = ["https://link.com"]

    # Run the function in test mode (uses FAKE_TEAM_SOURCES instead of real one)
    result = scrape_landing_pages_for_url_extractions(test=True)

    # Assert top-level output is a dictionary
    assert isinstance(result, dict)

    # Check that each team has a sub-dictionary of URLs
    for team, urls in result.items():
        assert isinstance(urls, dict)

        # Check that each source URL maps to a list of strings (links)
        for source, links in urls.items():
            assert isinstance(links, list)
            assert all(isinstance(link, str) for link in links)


@patch("scraping_news.get_relevant_articles.Website")
@patch("scraping_news.get_relevant_articles.TEAM_NEWS_SOURCES_test", FAKE_TEAM_SOURCES)
def test_team_keys_match_source_dict(mock_website):
    """
    Test that the top-level keys in the returned dictionary exactly match the team names
    defined in the fake test source config.

    This ensures that:
    - Every team from the input is represented in the output.
    - No teams are missing or unexpectedly added.

    The Website class is mocked to avoid live HTTP requests, and the test config is replaced
    with a controlled FAKE_TEAM_SOURCES dictionary.
    """

    # Mock the links returned by Website.get_links()
    mock_website.return_value.get_links.return_value = ["https://link.com"]

    # Run the scraping function using the fake config
    result = scrape_landing_pages_for_url_extractions(test=True)

    # Confirm that the keys (team names) in the result match the fake config exactly
    assert set(result.keys()) == set(FAKE_TEAM_SOURCES.keys())


@patch("scraping_news.get_relevant_articles.Website")
@patch("scraping_news.get_relevant_articles.TEAM_NEWS_SOURCES_test", FAKE_TEAM_SOURCES)
def test_empty_sources_yield_empty_lists(mock_website):
    """
    Test that when Website.get_links() returns an empty list (no links found),
    the function still includes the correct structure in the output — with empty lists.

    This ensures that:
    - The function doesn't crash or skip entries when no links are returned.
    - It properly handles valid pages that simply have no <a> tags.
    - The data schema is preserved even for empty results.

    Website is mocked to simulate a real scrape returning no links.
    The test config is patched with FAKE_TEAM_SOURCES for controlled input.
    """

    # Simulate no links found on the page
    mock_website.return_value.get_links.return_value = []

    # Run the function with test config
    result = scrape_landing_pages_for_url_extractions(test=True)

    # Check that all returned values (lists of links) are empty
    for team_sources in result.values():
        for links in team_sources.values():
            assert links == []


@patch("scraping_news.get_relevant_articles.Website")
@patch("scraping_news.get_relevant_articles.TEAM_NEWS_SOURCES_test", FAKE_TEAM_SOURCES)
def test_deduplication_of_links(mock_website):
    """
    Test that the function removes duplicate URLs returned by Website.get_links().

    This ensures that:
    - Each list of links in the result contains only unique entries.
    - The deduplication logic (via set()) is correctly applied.
    - Downstream consumers of the data won't have to handle duplicates manually.

    Website is mocked to return a list with intentional duplicates.
    The test config is patched to provide predictable team + source input.
    """

    # Simulate Website.get_links() returning duplicate URLs
    mock_website.return_value.get_links.return_value = [
        "https://example.com/article1",
        "https://example.com/article1",  # duplicate
        "https://example.com/article2"
    ]

    # Run the function with the test config
    result = scrape_landing_pages_for_url_extractions(test=True)

    # Check that each list of links contains only unique items
    for team_sources in result.values():
        for links in team_sources.values():
            assert len(links) == 2
            assert sorted(links) == sorted(set(links))

