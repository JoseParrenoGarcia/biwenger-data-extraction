import logging
from unittest.mock import MagicMock, patch
from scraping_news.get_relevant_articles import insert_deduplicated_articles_in_database

flat_rows = [
    {"team": "Valencia", "source": "source1", "url": "https://existing.com"},
    {"team": "Valencia", "source": "source1", "url": "https://new.com"},
]

def test_skips_if_table_does_not_exist(caplog):
    """
    Should skip insert if the table does not exist in Supabase.
    """
    logger = logging.getLogger("test_logger")

    with patch("scraping_news.get_relevant_articles.get_supabase_client") as mock_client, \
         patch("scraping_news.get_relevant_articles.check_if_table_exists", return_value=False):

        insert_deduplicated_articles_in_database(
            flat_rows=flat_rows,
            table_name="non_existent_table",
            logger=logger
        )

        assert "does not exist" in caplog.text

def test_filters_out_duplicates():
    """
    Should only insert non-duplicate rows when some already exist.
    """
    logger = logging.getLogger("test_logger")

    mock_supabase = MagicMock()
    mock_response = MagicMock()
    mock_response.data = [{"team": "Valencia", "url": "https://existing.com"}]
    mock_supabase.table.return_value.select.return_value.execute.return_value = mock_response

    with patch("scraping_news.get_relevant_articles.get_supabase_client", return_value=mock_supabase), \
         patch("scraping_news.get_relevant_articles.check_if_table_exists", return_value=True), \
         patch("scraping_news.get_relevant_articles.insert_rows_into_table") as mock_insert:

        insert_deduplicated_articles_in_database(
            flat_rows=flat_rows,
            table_name="article_urls",
            logger=logger
        )

        mock_insert.assert_called_once()
        inserted_rows = mock_insert.call_args[1]["rows"]
        assert len(inserted_rows) == 1
        assert inserted_rows[0]["url"] == "https://new.com"

def test_skips_write_if_no_new_rows():
    """
    Should skip insert operation if all rows are duplicates.
    """
    logger = logging.getLogger("test_logger")

    mock_supabase = MagicMock()
    mock_response = MagicMock()
    mock_response.data = [{"team": "Valencia", "url": "https://existing.com"}]
    mock_supabase.table.return_value.select.return_value.execute.return_value = mock_response

    with patch("scraping_news.get_relevant_articles.get_supabase_client", return_value=mock_supabase), \
         patch("scraping_news.get_relevant_articles.check_if_table_exists", return_value=True), \
         patch("scraping_news.get_relevant_articles.insert_rows_into_table") as mock_insert:

        insert_deduplicated_articles_in_database(
            flat_rows=[{"team": "Valencia", "source": "source1", "url": "https://existing.com"}],
            table_name="article_urls",
            logger=logger
        )

        mock_insert.assert_not_called()
