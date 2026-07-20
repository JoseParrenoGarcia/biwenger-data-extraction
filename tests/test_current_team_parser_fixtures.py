from pathlib import Path

from scraping_biwenger.current_team.html_parsers import parse_current_team_table_html
from scraping_biwenger.current_team.transform import CURRENT_TEAM_COLUMNS, transform_current_team

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "biwenger"


def _fixture_text(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


def test_parse_current_team_table_html_fixture():
    raw_df = parse_current_team_table_html(_fixture_text("current_team_table.html"))
    df = transform_current_team(raw_df)

    assert list(df.columns) == CURRENT_TEAM_COLUMNS
    assert df.to_dict(orient="records") == [
        {
            "name": "Mbappé",
            "position_short": "F",
            "position": "Forward",
            "team_name": "Real Madrid",
            "player_slug": "mbappe",
            "player_url": "/la-liga/players/mbappe",
            "points": 298,
            "previous_season_points": 284,
            "market_value": 22950000,
            "mv_change_eur": -50000,
            "status": "fit",
            "games_played": 31,
            "average_points": 9.6,
            "home_points": 140,
            "home_average_points": 9.3,
            "away_points": 158,
            "away_average_points": 9.9,
            "next_fixture_location": "Home",
            "next_opponent": "Barcelona",
            "next_match_url": "/la-liga/matches/2026-2027/round-1/real-madrid/barcelona/50724",
            "next_match_id": 50724,
            "form_t-1": 10,
            "form_t-2": 8,
            "form_t-3": 6,
            "form_t-4": 4,
            "form_t-5": 2,
        }
    ]
