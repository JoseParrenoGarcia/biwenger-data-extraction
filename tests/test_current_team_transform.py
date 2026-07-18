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
                "points": "123",
                "market_value": "12000000",
                "mv_change_eur": "-50000",
                "status": " fit ",
                "games_played": "8",
                "average_points": "6.5",
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
    assert result.loc[0, "points"] == 123
    assert result.loc[0, "mv_change_eur"] == -50000
    assert result.loc[0, "form_t-3"] == 0
    assert result.loc[0, "average_points"] == 6.5


def test_transform_current_team_rejects_missing_required_columns():
    with pytest.raises(ValueError, match="missing columns"):
        transform_current_team(pd.DataFrame([{"name": "Mbappe"}]))


def test_validate_current_team_payload_rejects_empty_dataframes():
    with pytest.raises(ValueError, match="empty"):
        validate_current_team_payload(pd.DataFrame(columns=CURRENT_TEAM_COLUMNS))
