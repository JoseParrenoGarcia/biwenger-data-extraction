from scraping_biwenger.players.scrape import scrape_player_rows


class FakeLogger:
    def __init__(self):
        self.messages = []

    def info(self, *args):
        self.messages.append(args)

    def warning(self, *args):
        self.messages.append(args)


def _players(count=3):
    return [
        {
            "name": f"Player {idx}",
            "slug": f"player-{idx}",
            "href": f"/la-liga/players/player-{idx}",
        }
        for idx in range(1, count + 1)
    ]


def test_retry_top_player_failure_once(monkeypatch):
    calls = []
    payload_players = []
    errors = []

    def fake_detail_loop(logger, page, players, **kwargs):
        calls.append(players)
        details = []
        for player in players:
            if player["slug"] == "player-2" and player.get("attempt") == "initial":
                kwargs["on_player_error"](
                    player=player,
                    stage="select_scoring_system",
                    message="Timeout waiting for scoring menu",
                )
                continue
            detail = {
                "player_name": player["name"],
                "team": "Athletic",
                "slug": player["slug"],
            }
            details.append(detail)
            kwargs["on_player_payload"](
                player=player,
                detail_rows=[detail],
                match_rows=[],
                value_history_rows=[],
                processed_count=len(details),
            )
        return details, [], []

    monkeypatch.setattr("scraping_biwenger.players.scrape.select_player_table_layout", lambda page, logger=None: None)
    monkeypatch.setattr(
        "scraping_biwenger.players.scrape.extract_all_player_names",
        lambda logger, page, max_pages, max_players=None: _players(),
    )
    monkeypatch.setattr("scraping_biwenger.players.scrape.scrape_all_players_detail", fake_detail_loop)

    _, detail_rows, _, _ = scrape_player_rows(
        object(),
        FakeLogger(),
        max_pages=1,
        max_players_detail=3,
        retry_top_players=2,
        on_player_payload=lambda **kwargs: payload_players.append(kwargs["player"]),
        on_player_error=lambda **kwargs: errors.append(kwargs),
    )

    assert len(calls) == 2
    assert calls[1][0]["slug"] == "player-2"
    assert calls[1][0]["attempt"] == "retry"
    assert calls[1][0]["open_by_href_only"] is True
    assert len(detail_rows) == 3
    assert [player["slug"] for player in payload_players] == ["player-1", "player-3", "player-2"]
    assert errors[0]["player"]["attempt"] == "initial"


def test_player_outside_retry_cap_is_not_retried(monkeypatch):
    calls = []

    def fake_detail_loop(logger, page, players, **kwargs):
        calls.append(players)
        for player in players:
            if player["slug"] == "player-3":
                kwargs["on_player_error"](
                    player=player,
                    stage="open_player",
                    message="Could not open detail",
                )
        return [], [], []

    monkeypatch.setattr("scraping_biwenger.players.scrape.select_player_table_layout", lambda page, logger=None: None)
    monkeypatch.setattr(
        "scraping_biwenger.players.scrape.extract_all_player_names",
        lambda logger, page, max_pages, max_players=None: _players(),
    )
    monkeypatch.setattr("scraping_biwenger.players.scrape.scrape_all_players_detail", fake_detail_loop)

    scrape_player_rows(
        object(),
        FakeLogger(),
        max_pages=1,
        max_players_detail=3,
        retry_top_players=2,
    )

    assert len(calls) == 1


def test_partial_success_match_failure_is_not_retried(monkeypatch):
    calls = []
    errors = []

    def fake_detail_loop(logger, page, players, **kwargs):
        calls.append(players)
        detail = {
            "player_name": players[0]["name"],
            "team": "Athletic",
            "slug": players[0]["slug"],
        }
        kwargs["on_player_error"](
            player=players[0],
            stage="scrape_matches",
            message="Match table unavailable",
        )
        if kwargs["on_player_payload"]:
            kwargs["on_player_payload"](
                player=players[0],
                detail_rows=[detail],
                match_rows=[],
                value_history_rows=[],
                processed_count=1,
            )
        return [detail], [], []

    monkeypatch.setattr("scraping_biwenger.players.scrape.select_player_table_layout", lambda page, logger=None: None)
    monkeypatch.setattr(
        "scraping_biwenger.players.scrape.extract_all_player_names",
        lambda logger, page, max_pages, max_players=None: _players(1),
    )
    monkeypatch.setattr("scraping_biwenger.players.scrape.scrape_all_players_detail", fake_detail_loop)

    _, detail_rows, _, _ = scrape_player_rows(
        object(),
        FakeLogger(),
        max_pages=1,
        max_players_detail=1,
        retry_top_players=1,
        on_player_error=lambda **kwargs: errors.append(kwargs),
    )

    assert len(calls) == 1
    assert len(detail_rows) == 1
    assert errors[0]["stage"] == "scrape_matches"


def test_retry_failure_is_recorded_once_without_second_retry(monkeypatch):
    calls = []
    errors = []

    def fake_detail_loop(logger, page, players, **kwargs):
        calls.append(players)
        for player in players:
            kwargs["on_player_error"](
                player=player,
                stage="select_scoring_system",
                message="Still failing",
            )
        return [], [], []

    monkeypatch.setattr("scraping_biwenger.players.scrape.select_player_table_layout", lambda page, logger=None: None)
    monkeypatch.setattr(
        "scraping_biwenger.players.scrape.extract_all_player_names",
        lambda logger, page, max_pages, max_players=None: _players(1),
    )
    monkeypatch.setattr("scraping_biwenger.players.scrape.scrape_all_players_detail", fake_detail_loop)

    scrape_player_rows(
        object(),
        FakeLogger(),
        max_pages=1,
        max_players_detail=1,
        retry_top_players=1,
        on_player_error=lambda **kwargs: errors.append(kwargs),
    )

    assert len(calls) == 2
    assert len(errors) == 2
    assert errors[0]["player"]["attempt"] == "initial"
    assert errors[1]["player"]["attempt"] == "retry"
