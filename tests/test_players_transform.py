import pandas as pd
import pytest

from scraping_biwenger.players.matches import _get_season_label, _points_content_is_loaded
from scraping_biwenger.players.transform import (
    PLAYER_MATCHES_COLUMNS,
    PLAYER_STATS_COLUMNS,
    PLAYER_VALUE_COLUMNS,
    transform_player_outputs,
    validate_player_payloads,
)


class _FakeLocator:
    def __init__(self, text: str = "", count: int = 0, attrs: dict | None = None):
        self._text = text
        self._count = count
        self._attrs = attrs or {}

    @property
    def first(self):
        return self

    def count(self):
        return self._count

    def inner_text(self):
        return self._text

    def get_attribute(self, name):
        return self._attrs.get(name)


class _FakePage:
    def __init__(self, locators: dict[str, _FakeLocator], url: str = "https://biwenger.as.com/app"):
        self._locators = locators
        self.url = url

    def locator(self, selector: str):
        return self._locators.get(selector, _FakeLocator())


def test_get_season_label_prefers_visible_season_button():
    page = _FakePage(
        {
            'player-detail-points button[modalmenutitle="Season"]': _FakeLocator(
                text=" 2025/2026 season ",
                count=1,
            ),
        },
        url="https://biwenger.as.com/app?season=2026-2027",
    )

    assert _get_season_label(page) == "2025/2026"


def test_get_season_label_normalizes_url_fallback():
    page = _FakePage({}, url="https://biwenger.as.com/app?season=2026-2027")

    assert _get_season_label(page) == "2026/2027"


def test_points_content_is_loaded_for_no_rounds_message():
    page = _FakePage(
        {
            "player-detail-points": _FakeLocator(
                text="2025/2026 season AS.com and SofaScore average Hasn't played any round yet",
                count=1,
            ),
        }
    )

    assert _points_content_is_loaded(page) is True


def test_points_content_is_loaded_for_no_rounds_message_with_curly_apostrophe():
    page = _FakePage(
        {
            "player-detail-points": _FakeLocator(
                text="Hasn’t played any round yet",
                count=1,
            ),
        }
    )

    assert _points_content_is_loaded(page) is True


def test_transform_player_outputs_normalizes_three_payloads():
    stats_rows = [
        {
            "player_name": "  Player One  ",
            "team": " Athletic ",
            "position": " Forward ",
            "status": " Fit ",
            "status_detail": "",
            "scoring_system": " sofascore ",
            "points": "42",
            "value": "1200000",
            "min_value": "1000000",
            "max_value": "1500000",
            "matches_played": "6",
            "average": "7.0",
            "market_purchases_pct": "12.5",
            "market_sales_pct": "3",
            "market_usage_pct": None,
            "season": "2026/2027",
            "name": "ignored duplicate source field",
            "slug": "player-one",
            "href": "/la-liga/players/ignored-slug",
        }
    ]
    match_rows = [
        {
            "season_label": "2026/2027",
            "round_label": "Round 1",
            "match_date": "2026-08-20",
            "points": "8",
            "best_xi": True,
            "events": [{"type": "goal"}],
            "player_name": "Player One",
            "team": "Athletic",
            "slug": "player-one",
            "scoring_system": "sofascore",
        },
        {
            "season_label": "2026/2027",
            "round_label": "Round 1",
            "match_date": "2026-08-20",
            "points": "8",
            "best_xi": True,
            "events": [{"type": "goal"}],
            "player_name": "Player One",
            "team": "Athletic",
            "slug": "player-one",
            "scoring_system": "sofascore",
        },
    ]
    value_rows = [
        {
            "slug": "player-one",
            "player_name": "Player One",
            "team": "Athletic",
            "date": "2026-08-20",
            "market_value_eur": "1200000",
        },
        {
            "slug": "player-one",
            "player_name": "Player One",
            "team": "Athletic",
            "date": "not a date",
            "market_value_eur": "bad number",
        },
    ]

    stats_df, matches_df, value_df = transform_player_outputs(
        stats_rows,
        match_rows,
        value_rows,
        as_of_date="2026-07-18",
    )

    assert list(stats_df.columns) == PLAYER_STATS_COLUMNS
    assert list(matches_df.columns) == PLAYER_MATCHES_COLUMNS
    assert list(value_df.columns) == PLAYER_VALUE_COLUMNS
    assert stats_df.loc[0, "player_name"] == "Player One"
    assert stats_df.loc[0, "team"] == "Athletic"
    assert stats_df.loc[0, "slug"] == "player-one"
    assert stats_df.loc[0, "status_detail"] is None
    assert stats_df.loc[0, "scoring_system"] == "sofascore"
    assert stats_df.loc[0, "points"] == 42
    assert stats_df.loc[0, "market_usage_pct"] == 0.0
    assert stats_df.loc[0, "as_of_date"] == "2026-07-18"
    assert len(matches_df) == 1
    assert matches_df.loc[0, "match_date"] == "2026-08-20"
    assert matches_df.loc[0, "slug"] == "player-one"
    assert matches_df.loc[0, "scoring_system"] == "sofascore"
    assert matches_df.loc[0, "as_of_date"] == "2026-07-18"
    assert len(value_df) == 1
    assert value_df.loc[0, "date"] == "2026-08-20"
    assert value_df.loc[0, "market_value_eur"] == 1200000


def test_transform_player_outputs_returns_empty_payload_shapes():
    stats_df, matches_df, value_df = transform_player_outputs([], [], [])

    assert list(stats_df.columns) == PLAYER_STATS_COLUMNS
    assert list(matches_df.columns) == PLAYER_MATCHES_COLUMNS
    assert list(value_df.columns) == PLAYER_VALUE_COLUMNS
    assert stats_df.empty
    assert matches_df.empty
    assert value_df.empty


def test_transform_player_outputs_defaults_scoring_system_to_sofascore():
    stats_df, _, _ = transform_player_outputs(
        [
            {
                "player_name": "Player One",
                "team": "Athletic",
            }
        ],
        [],
        [],
        as_of_date="2026-07-18",
    )

    assert stats_df.loc[0, "scoring_system"] == "sofascore"


def test_transform_player_outputs_keeps_duplicate_names_when_slugs_differ():
    stats_df, _, _ = transform_player_outputs(
        [
            {
                "player_name": "Moussa Diarra",
                "team": "Alavés",
                "slug": "moussa-diarra",
                "points": 5,
            },
            {
                "player_name": "Moussa Diarra",
                "team": "Alavés",
                "slug": "moussa-diarra-2",
                "points": 2,
            },
        ],
        [],
        [],
        as_of_date="2026-07-19",
    )

    assert len(stats_df) == 2
    assert set(stats_df["slug"]) == {"moussa-diarra", "moussa-diarra-2"}


def test_validate_player_payloads_rejects_missing_columns():
    with pytest.raises(ValueError, match="missing columns"):
        validate_player_payloads(
            pd.DataFrame([{"player_name": "Player One"}]),
            pd.DataFrame(columns=PLAYER_MATCHES_COLUMNS),
            pd.DataFrame(columns=PLAYER_VALUE_COLUMNS),
        )
