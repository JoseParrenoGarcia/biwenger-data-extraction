import pytest
from unittest.mock import patch, MagicMock
from scraping_news.get_specialised_articles import scrape_match_preview_links


@pytest.fixture
def fake_logger():
    import logging
    return logging.getLogger("test_logger")


# ✅ Test 1: Normal case with clean partido links
def test_scrape_match_preview_links_adds_previa(fake_logger):
    """
    Given a base URL that returns valid partido links,
    ensure scrape_match_preview_links returns /previa-appended unique links.
    """
    fake_links = [
        "https://www.jornadaperfecta.com/partido/1234/osasuna-valencia",
        "https://www.jornadaperfecta.com/partido/5678/athletic-rayo"
    ]

    with patch("scraping_news.get_specialised_articles.Website") as mock_website:
        mock_instance = MagicMock()
        mock_instance.get_links.return_value = fake_links
        mock_website.return_value = mock_instance

        result = scrape_match_preview_links(logger=fake_logger)

    expected = {
        "https://www.jornadaperfecta.com/partido/1234/osasuna-valencia/previa",
        "https://www.jornadaperfecta.com/partido/5678/athletic-rayo/previa"
    }

    assert set(result) == expected


# ✅ Test 2: Handles duplicate links
def test_scrape_match_preview_links_deduplicates(fake_logger):
    fake_links = [
        "https://www.jornadaperfecta.com/partido/1234/osasuna-valencia",
        "https://www.jornadaperfecta.com/partido/1234/osasuna-valencia"  # duplicate
    ]

    with patch("scraping_news.get_specialised_articles.Website") as mock_website:
        mock_instance = MagicMock()
        mock_instance.get_links.return_value = fake_links
        mock_website.return_value = mock_instance

        result = scrape_match_preview_links(logger=fake_logger)

    assert result == [
        "https://www.jornadaperfecta.com/partido/1234/osasuna-valencia/previa"
    ]


# ✅ Test 3: Website constructor throws error
def test_scrape_match_preview_links_handles_exception(fake_logger):
    with patch("scraping_news.get_specialised_articles.Website", side_effect=Exception("Network error")):
        result = scrape_match_preview_links(logger=fake_logger)

    assert result == []
