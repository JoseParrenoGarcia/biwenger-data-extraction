import pytest
from unittest.mock import patch, MagicMock
from scraping_news.get_article_contents import get_urls_to_scrape

# Logger fixture to avoid needing to instantiate logging each time
@pytest.fixture
def fake_logger():
    import logging
    return logging.getLogger("test_logger")

# Reusable mocked Supabase client
@pytest.fixture
def fake_supabase():
    return MagicMock()


# ✅ Test 1: Normal case with filtering
def test_get_urls_to_scrape_filters_existing(fake_supabase, fake_logger):
    """
    Given a list of articles from article_urls,
    and a set of article_ids already present in article_contents,
    this test checks that only the new (non-duplicated) articles are returned.
    """
    all_articles = [
        {"id": 1, "url": "url1", "team": "A", "source": "sourceA"},
        {"id": 2, "url": "url2", "team": "B", "source": "sourceB"},
        {"id": 3, "url": "url3", "team": "C", "source": "sourceC"}
    ]
    mock_response = MagicMock()
    mock_response.data = all_articles

    # Simulate supabase.table(...).select(...).execute()
    fake_supabase.table.return_value.select.return_value.execute.return_value = mock_response

    # Mock existing article IDs as {1, 3}
    with patch("scraping_news.get_article_contents.get_existing_article_ids", return_value={1, 3}):
        result = get_urls_to_scrape(fake_supabase, fake_logger)

    # Only article 2 should remain (not yet processed)
    assert result == [{"id": 2, "url": "url2", "team": "B", "source": "sourceB"}]


# ❌ Test 2: Supabase fails to fetch article URLs
def test_get_urls_to_scrape_supabase_error(fake_supabase, fake_logger):
    """
    Simulates an exception being raised by Supabase when fetching article_urls.
    The function should handle the exception and return an empty list.
    """
    # Raise error when trying to execute select()
    fake_supabase.table.return_value.select.return_value.execute.side_effect = Exception("DB error")

    # Doesn't matter what get_existing_article_ids returns; shouldn't be called
    with patch("scraping_news.get_article_contents.get_existing_article_ids", return_value=set()):
        result = get_urls_to_scrape(fake_supabase, fake_logger)

    assert result == []


# ⚠️ Test 3: No article_contents rows exist
def test_get_urls_to_scrape_no_existing_ids(fake_supabase, fake_logger):
    """
    If the article_contents table is empty (i.e., no existing article IDs),
    all rows from article_urls should be returned for scraping.
    """
    all_articles = [
        {"id": 10, "url": "x", "team": "X", "source": "X"},
        {"id": 20, "url": "y", "team": "Y", "source": "Y"}
    ]
    mock_response = MagicMock()
    mock_response.data = all_articles

    fake_supabase.table.return_value.select.return_value.execute.return_value = mock_response

    # Simulate article_contents being empty
    with patch("scraping_news.get_article_contents.get_existing_article_ids", return_value=set()):
        result = get_urls_to_scrape(fake_supabase, fake_logger)

    # All input articles should be returned
    assert result == all_articles


# 🧪 Test 4: All article_urls are already processed
def test_get_urls_to_scrape_all_urls_already_scraped(fake_supabase, fake_logger):
    """
    Simulates the case where all article_urls have already been scraped.
    The function should return an empty list after filtering.
    """
    all_articles = [
        {"id": 1, "url": "a", "team": "A", "source": "A"},
        {"id": 2, "url": "b", "team": "B", "source": "B"}
    ]
    mock_response = MagicMock()
    mock_response.data = all_articles

    fake_supabase.table.return_value.select.return_value.execute.return_value = mock_response

    # All IDs already exist
    with patch("scraping_news.get_article_contents.get_existing_article_ids", return_value={1, 2}):
        result = get_urls_to_scrape(fake_supabase, fake_logger)

    assert result == []
