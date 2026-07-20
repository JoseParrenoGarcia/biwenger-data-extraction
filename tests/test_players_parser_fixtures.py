from pathlib import Path

from scraping_biwenger.players.html_parsers import (
    parse_player_detail_html,
    parse_player_matches_html,
)
from scraping_biwenger.players.value_history import parse_value_csv_text

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "biwenger"


def _fixture_text(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


def test_parse_player_detail_html_fixture():
    detail = parse_player_detail_html(_fixture_text("player_detail_mbappe.html"))

    assert detail == {
        "player_name": "Mbappé",
        "team": "Real Madrid",
        "position": "Forward",
        "status": "fit",
        "status_detail": "Fit",
        "points": 298,
        "value": 22950000,
        "min_value": 20750000,
        "max_value": 31490000,
        "matches_played": 31,
        "average": 9.6,
        "market_purchases_pct": 94.0,
        "market_sales_pct": 5.0,
        "market_usage_pct": 17.0,
        "season": "2025/2026",
    }


def test_parse_player_matches_html_fixture():
    rows = parse_player_matches_html(_fixture_text("player_matches_mbappe.html"))

    assert rows == [
        {
            "season_label": "2025/2026",
            "round_label": "R1",
            "match_date": "2025-08-19",
            "points": 14,
            "best_xi": False,
            "events": "",
        },
        {
            "season_label": "2025/2026",
            "round_label": "R2",
            "match_date": "2025-08-24",
            "points": 19,
            "best_xi": True,
            "events": "Goal | Best XI",
        },
    ]


def test_parse_player_matches_no_rounds_fixture_returns_empty_rows():
    rows = parse_player_matches_html(_fixture_text("player_matches_no_rounds.html"))

    assert rows == []


def test_parse_value_csv_text_fixture_normalizes_dates_and_values():
    df = parse_value_csv_text(_fixture_text("player_value_history.csv"))

    assert list(df.columns) == ["date", "market_value_eur"]
    assert df.to_dict(orient="records") == [
        {"date": "2025-07-19", "market_value_eur": 23010000},
        {"date": "2025-07-20", "market_value_eur": 23130000},
    ]
