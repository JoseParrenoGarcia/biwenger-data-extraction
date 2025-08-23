from scraping_news.get_relevant_articles import flatten_filtered_links_dict

def test_flatten_structure_correctness():
    """
    Test that the function correctly flattens nested dictionary into list of rows with 'team', 'source', 'url'.
    """
    input_dict = {
        "Valencia": {
            "https://source1.com": ["https://article1.com", "https://article2.com"],
            "https://source2.com": ["https://article3.com"]
        }
    }

    expected = [
        {"team": "Valencia", "source": "https://source1.com", "url": "https://article1.com"},
        {"team": "Valencia", "source": "https://source1.com", "url": "https://article2.com"},
        {"team": "Valencia", "source": "https://source2.com", "url": "https://article3.com"}
    ]

    result = flatten_filtered_links_dict(input_dict)
    assert result == expected

def test_empty_input_returns_empty_list():
    """
    If input dict is empty, return should also be an empty list.
    """
    result = flatten_filtered_links_dict({})
    assert result == []

def test_single_entry_flattens_correctly():
    """
    One team, one source, one link should return a list with one dictionary.
    """
    input_dict = {
        "Real Madrid": {
            "https://marca.com": ["https://marca.com/news"]
        }
    }

    expected = [
        {"team": "Real Madrid", "source": "https://marca.com", "url": "https://marca.com/news"}
    ]

    result = flatten_filtered_links_dict(input_dict)
    assert result == expected

def test_team_with_empty_sources_is_skipped():
    """
    A team with an empty source dictionary should result in no rows.
    """
    input_dict = {
        "Atletico": {}
    }

    result = flatten_filtered_links_dict(input_dict)
    assert result == []

def test_source_with_empty_links_is_skipped():
    """
    Sources that have empty link lists should not generate any rows.
    """
    input_dict = {
        "Sevilla": {
            "https://empty.com": [],
            "https://filled.com": ["https://news.com"]
        }
    }

    expected = [
        {"team": "Sevilla", "source": "https://filled.com", "url": "https://news.com"}
    ]

    result = flatten_filtered_links_dict(input_dict)
    assert result == expected
