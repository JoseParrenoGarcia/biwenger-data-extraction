import pandas as pd
import pytest

from scraping_biwenger.current_team import persist


def _valid_current_team_df():
    return pd.DataFrame(
        [
            {
                "name": "Mbappe",
                "position_short": "F",
                "position": "Forward",
                "team_name": "Real Madrid",
                "player_slug": "mbappe",
                "player_url": "/la-liga/players/mbappe",
                "points": 123,
                "previous_season_points": 284,
                "market_value": 12000000,
                "mv_change_eur": -50000,
                "status": "fit",
                "games_played": 8,
                "average_points": 6.5,
                "home_points": 70,
                "home_average_points": 7.0,
                "away_points": 53,
                "away_average_points": 5.3,
                "next_fixture_location": "Home",
                "next_opponent": "Barcelona",
                "next_match_url": "/la-liga/matches/2026-2027/round-1/home/away/50724",
                "next_match_id": 50724,
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
    monkeypatch.setattr(persist, "current_team_table_exists", lambda supabase, table_name: False)

    with pytest.raises(RuntimeError, match="Run the schema bootstrap"):
        persist.insert_current_team(
            _valid_current_team_df(),
            table_name="biwenger_current_team",
            supabase=object(),
        )


def test_insert_current_team_uses_admin_client_by_default(monkeypatch):
    sentinel = object()
    seen = {}

    monkeypatch.setattr(persist, "get_supabase_admin_client", lambda: sentinel)
    monkeypatch.setattr(persist, "current_team_table_exists", lambda supabase, table_name: True)

    def fake_insert_current_team_rows(supabase, table_name, df):
        seen["supabase"] = supabase
        seen["table_name"] = table_name
        seen["rows"] = len(df)

    monkeypatch.setattr(persist, "insert_current_team_rows", fake_insert_current_team_rows)

    persist.insert_current_team(_valid_current_team_df(), table_name="biwenger_current_team")

    assert seen == {
        "supabase": sentinel,
        "table_name": "biwenger_current_team",
        "rows": 1,
    }
