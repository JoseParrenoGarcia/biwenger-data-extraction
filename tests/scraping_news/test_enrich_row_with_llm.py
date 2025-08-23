import pytest
import textwrap
from unittest.mock import patch
from scraping_news.get_article_contents import enrich_row_with_llm

@pytest.fixture
def fake_logger():
    import logging
    return logging.getLogger("test_logger")

# ✅ Test 1: LLM returns valid structured JSON
def test_enrich_row_valid_llm_output(fake_logger):
    """
    Simulates a valid LLM response with all expected fields.
    The row should be enriched accordingly.
    """
    row = {
        "raw_text": "Este es el contenido del artículo...",
        "title": "Lesión de Gaya preocupa al Valencia"
    }

    fake_llm_output = textwrap.dedent("""\
        {
            "summary": "Gayà se lesiona y estará fuera 3 semanas.",
            "tags_llm": ["lesiones_sanciones"],
            "recognised_teams_llm": ["Valencia"],
            "recognised_people_llm": ["Gayà"]
        }
    """)

    with patch("scraping_news.get_article_contents.prompt_article_summary_and_tags") as mock_prompt, \
         patch("scraping_news.get_article_contents.call_llm", return_value=fake_llm_output), \
         patch("scraping_news.get_article_contents.extract_code_block", return_value=fake_llm_output):

        mock_prompt.return_value = ("SYS", "USER")

        result = enrich_row_with_llm(row.copy(), fake_logger)

    assert result["summary_llm"] == "Gayà se lesiona y estará fuera 3 semanas."
    assert result["tags_llm"] == ["lesiones_sanciones"]
    assert result["recognised_teams_llm"] == ["Valencia"]
    assert result["recognised_people_llm"] == ["Gayà"]

# ⚠️ Test 2: LLM output is missing optional fields
def test_enrich_row_llm_output_missing_keys(fake_logger):
    """
    Simulates a valid LLM response that omits some keys.
    Function should still work and fall back to empty lists.
    """
    row = {
        "raw_text": "Artículo sobre fichajes.",
        "title": "Valencia ficha delantero"
    }

    partial_output = textwrap.dedent("""\
        {
            "summary": "El Valencia ficha a un delantero joven."
        }
    """)

    with patch("scraping_news.get_article_contents.prompt_article_summary_and_tags") as mock_prompt, \
         patch("scraping_news.get_article_contents.call_llm", return_value=partial_output), \
         patch("scraping_news.get_article_contents.extract_code_block", return_value=partial_output):

        mock_prompt.return_value = ("SYS", "USER")
        result = enrich_row_with_llm(row.copy(), fake_logger)

    assert result["summary_llm"] == "El Valencia ficha a un delantero joven."
    assert result["tags_llm"] == []
    assert result["recognised_teams_llm"] == []
    assert result["recognised_people_llm"] == []

# 💥 Test 3: Malformed LLM response
def test_enrich_row_malformed_llm_output(fake_logger):
    """
    If the LLM returns a non-parseable string,
    enrich_row_with_llm should catch the exception and return None.
    """
    row = {
        "raw_text": "Artículo...",
        "title": "Error parsing"
    }

    invalid_output = "This is not valid JSON or Python dict"

    with patch("scraping_news.get_article_contents.prompt_article_summary_and_tags") as mock_prompt, \
         patch("scraping_news.get_article_contents.call_llm", return_value=invalid_output), \
         patch("scraping_news.get_article_contents.extract_code_block", return_value=invalid_output):

        mock_prompt.return_value = ("SYS", "USER")
        result = enrich_row_with_llm(row.copy(), fake_logger)

    assert result is None

# ❌ Test 4: Empty LLM response
def test_enrich_row_empty_llm_response(fake_logger):
    """
    Simulates an empty LLM output (no content returned).
    Should be treated as failure.
    """
    row = {
        "raw_text": "Artículo de prueba",
        "title": "Sin respuesta"
    }

    with patch("scraping_news.get_article_contents.prompt_article_summary_and_tags") as mock_prompt, \
         patch("scraping_news.get_article_contents.call_llm", return_value=""), \
         patch("scraping_news.get_article_contents.extract_code_block", return_value=""):

        mock_prompt.return_value = ("SYS", "USER")
        result = enrich_row_with_llm(row.copy(), fake_logger)

    assert result is None
