import pandas as pd
import pytest

from scraping_biwenger.current_team import persist


def _valid_current_team_df():
    return pd.DataFrame(
        [
            {
                "name": "Mbappe",
                "points": 123,
                "market_value": 12000000,
                "mv_change_eur": -50000,
                "status": "fit",
                "games_played": 8,
                "average_points": 6.5,
                "form_t-1": 10,
                "form_t-2": 8,
                "form_t-3": 0,
                "form_t-4": 4,
                "form_t-5": 2,
            }
        ]
    )


def test_missing_table_message_points_to_bootstrap():
    message = persist.missing_table_message("biwenger_current_team")

    assert "biwenger_current_team" in message
    assert "schema bootstrap" in message


def test_insert_current_team_fails_clearly_when_table_is_missing(monkeypatch):
    monkeypatch.setattr(persist, "check_if_table_exists", lambda supabase, table_name: False)

    with pytest.raises(RuntimeError, match="Run the schema bootstrap"):
        persist.insert_current_team(
            _valid_current_team_df(),
            table_name="biwenger_current_team",
            supabase=object(),
        )
