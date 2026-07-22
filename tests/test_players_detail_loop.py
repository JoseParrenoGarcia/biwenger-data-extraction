import pandas as pd

from scraping_biwenger.players import detail_loop


class FakeLogger:
    def debug(self, *args, **kwargs):
        return None

    def info(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        return None

    def exception(self, *args, **kwargs):
        return None


def _base_player(slug: str, href: str | None = None) -> dict:
    player = {"name": slug.replace("-", " ").title(), "slug": slug}
    if href is not None:
        player["href"] = href
    return player


def _install_success_mocks(monkeypatch):
    monkeypatch.setattr(detail_loop, "open_player_detail", lambda *args, **kwargs: True)
    monkeypatch.setattr(detail_loop, "select_scoring_system", lambda *args, **kwargs: "sofascore")
    monkeypatch.setattr(
        detail_loop,
        "scrape_player_detail",
        lambda *args, **kwargs: {
            "player_name": "Mock Player",
            "team": "Mock Team",
            "points": 0,
            "value": 0,
            "matches_played": 0,
            "average": 0.0,
            "market_purchases_pct": 0.0,
            "market_sales_pct": 0.0,
        },
    )
    monkeypatch.setattr(detail_loop, "scrape_player_matches", lambda *args, **kwargs: [])
    monkeypatch.setattr(detail_loop, "with_retries", lambda fn, **kwargs: fn())
    monkeypatch.setattr(detail_loop, "scrape_value_history_for_player", lambda *args, **kwargs: pd.DataFrame())
    monkeypatch.setattr(detail_loop, "_cooldown", lambda *args, **kwargs: None)
    monkeypatch.setattr(detail_loop, "_log_timing", lambda *args, **kwargs: None)


def test_skip_back_to_table_when_next_player_has_href(monkeypatch):
    _install_success_mocks(monkeypatch)
    back_calls = []
    monkeypatch.setattr(
        detail_loop,
        "click_back_to_players_table",
        lambda *args, **kwargs: back_calls.append(True) or True,
    )
    monkeypatch.setattr(detail_loop, "clear_search_box_if_present", lambda *args, **kwargs: None)

    players = [
        _base_player("player-1", "/la-liga/players/player-1"),
        _base_player("player-2", "/la-liga/players/player-2"),
    ]

    detail_rows, match_rows, value_rows = detail_loop.scrape_all_players_detail(
        FakeLogger(),
        object(),
        players,
    )

    assert len(detail_rows) == 2
    assert match_rows == []
    assert value_rows == []
    assert back_calls == []


def test_back_to_table_when_next_player_needs_search(monkeypatch):
    _install_success_mocks(monkeypatch)
    back_calls = []
    monkeypatch.setattr(
        detail_loop,
        "click_back_to_players_table",
        lambda *args, **kwargs: back_calls.append(True) or True,
    )
    monkeypatch.setattr(detail_loop, "clear_search_box_if_present", lambda *args, **kwargs: None)

    players = [
        _base_player("player-1", "/la-liga/players/player-1"),
        _base_player("player-2"),
    ]

    detail_rows, match_rows, value_rows = detail_loop.scrape_all_players_detail(
        FakeLogger(),
        object(),
        players,
    )

    assert len(detail_rows) == 2
    assert match_rows == []
    assert value_rows == []
    assert back_calls == [True]
