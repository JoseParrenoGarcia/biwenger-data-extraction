import pandas as pd
import pytest

from scraping_biwenger.current_team.transform import (
    CURRENT_TEAM_COLUMNS,
    transform_current_team,
    validate_current_team_payload,
)


def test_transform_current_team_normalizes_payload_types():
    raw_df = pd.DataFrame(
        [
            {
                "name": "  Mbappe  ",
                "position_short": " F ",
                "position": " Forward ",
                "team_name": " Real Madrid ",
                "player_slug": " mbappe ",
                "player_url": "/la-liga/players/mbappe",
                "points": "123",
                "previous_season_points": "284",
                "market_value": "12000000",
                "mv_change_eur": "-50000",
                "status": " fit ",
                "games_played": "8",
                "average_points": "6.5",
                "home_points": "70",
                "home_average_points": "7.0",
                "away_points": "53",
                "away_average_points": "5.3",
                "next_fixture_location": " Home ",
                "next_opponent": " Barcelona ",
                "next_match_url": "/la-liga/matches/2026-2027/round-1/home/away/50724",
                "next_match_id": "50724",
                "form_t-1": "10",
                "form_t-2": "8",
                "form_t-3": None,
                "form_t-4": "4",
                "form_t-5": "2",
                "ignored": "not persisted",
            }
        ]
    )

    result = transform_current_team(raw_df)

    assert list(result.columns) == CURRENT_TEAM_COLUMNS
    assert result.loc[0, "name"] == "Mbappe"
    assert result.loc[0, "status"] == "fit"
    assert result.loc[0, "position_short"] == "F"
    assert result.loc[0, "position"] == "Forward"
    assert result.loc[0, "team_name"] == "Real Madrid"
    assert result.loc[0, "previous_season_points"] == 284
    assert result.loc[0, "points"] == 123
    assert result.loc[0, "mv_change_eur"] == -50000
    assert result.loc[0, "home_points"] == 70
    assert result.loc[0, "home_average_points"] == 7.0
    assert result.loc[0, "away_points"] == 53
    assert result.loc[0, "away_average_points"] == 5.3
    assert result.loc[0, "next_fixture_location"] == "Home"
    assert result.loc[0, "next_opponent"] == "Barcelona"
    assert result.loc[0, "next_match_id"] == 50724
    assert result.loc[0, "form_t-3"] == 0
    assert result.loc[0, "average_points"] == 6.5


def test_transform_current_team_keeps_optional_fields_nullable():
    raw_df = pd.DataFrame(
        [
            {
                column: None
                for column in CURRENT_TEAM_COLUMNS
            }
        ]
    )
    raw_df.loc[0, "name"] = "Nyland"
    raw_df.loc[0, "status"] = "Fit"

    result = transform_current_team(raw_df)

    assert result.loc[0, "team_name"] is None
    assert result.loc[0, "previous_season_points"] is None
    assert result.loc[0, "next_match_id"] is None
    assert result.loc[0, "home_points"] == 0
    assert result.loc[0, "home_average_points"] == 0.0


def test_transform_current_team_rejects_missing_required_columns():
    with pytest.raises(ValueError, match="missing columns"):
        transform_current_team(pd.DataFrame([{"name": "Mbappe"}]))


def test_validate_current_team_payload_rejects_empty_dataframes():
    with pytest.raises(ValueError, match="empty"):
        validate_current_team_payload(pd.DataFrame(columns=CURRENT_TEAM_COLUMNS))
