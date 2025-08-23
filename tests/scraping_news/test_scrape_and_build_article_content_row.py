import pytest
from unittest.mock import patch, MagicMock
from scraping_news.get_article_contents import scrape_and_build_article_content_row

@pytest.fixture
def fake_logger():
    import logging
    return logging.getLogger("test_logger")

# ✅ Test 1: Normal successful scrape
def test_scrape_and_build_valid_article(fake_logger):
    """
    Website returns a title, text, and published date → row is built correctly.
    """
    article = {"id": 123, "url": "https://example.com/news"}

    mock_website = MagicMock()
    mock_website.text = "This is the article content."
    mock_website.title = "Example Article Title"
    mock_website.published_at = "2025-08-23"

    with patch("scraping_news.get_article_contents.Website", return_value=mock_website):
        result = scrape_and_build_article_content_row(article, fake_logger)

    assert result == {
        "article_id": 123,
        "url": "https://example.com/news",
        "published_date": "2025-08-23",
        "raw_text": "This is the article content.",
        "title": "Example Article Title"
    }

# ⚠️ Test 2: Empty article text → should be skipped
def test_scrape_and_build_empty_text(fake_logger):
    """
    Website returns empty string as text → row is skipped (returns None).
    """
    article = {"id": 124, "url": "https://example.com/empty"}

    mock_website = MagicMock()
    mock_website.text = "     "  # Only whitespace
    mock_website.title = "Empty Title"
    mock_website.published_at = "2025-08-23"

    with patch("scraping_news.get_article_contents.Website", return_value=mock_website):
        result = scrape_and_build_article_content_row(article, fake_logger)

    assert result is None

# 💥 Test 3: Website scraping throws an exception
def test_scrape_and_build_website_failure(fake_logger):
    """
    If Website raises an exception during init → row is skipped (returns None).
    """
    article = {"id": 125, "url": "https://example.com/fail"}

    with patch("scraping_news.get_article_contents.Website", side_effect=Exception("Boom")):
        result = scrape_and_build_article_content_row(article, fake_logger)

    assert result is None
