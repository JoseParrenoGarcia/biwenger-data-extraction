# import sys
# import os
#
# # Get the absolute path to the project root (2 levels up)
# project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
# sys.path.insert(0, project_root)

import pytest
from unittest.mock import patch, Mock
from scraping_news.scraper_utils import Website
from requests.exceptions import RequestException


# 1. Simulate a valid HTML page with <a> tags
@patch("scraping_news.scraper_utils.requests.get")
def test_get_links_returns_expected_links(mock_get):
    """
    Test that Website.get_links() extracts valid URLs from HTML content.

    Mocks HTTP response with HTML containing relative, absolute, and javascript links.
    Verifies that relative URLs are converted to absolute and javascript links are filtered out.

    Expected: Returns list with absolute URLs only, excluding non-HTTP schemes.
    """
    html = """
    <html><body>
        <a href="/link1">Link 1</a>
        <a href="https://example.com/link2">Link 2</a>
        <a href="javascript:void(0)">Skip me</a>
    </body></html>
    """

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.headers = {"Content-Type": "text/html"}
    mock_response.content = html.encode("utf-8")

    mock_get.return_value = mock_response

    website = Website("https://example.com")
    links = website.get_links()

    assert isinstance(links, list)
    assert "https://example.com/link1" in links
    assert "https://example.com/link2" in links
    assert not any("javascript" in l for l in links)

