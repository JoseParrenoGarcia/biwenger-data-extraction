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
        lambda logger, page, max_pages, max_players=None, pacing_policy=None: _players(),
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
        lambda logger, page, max_pages, max_players=None, pacing_policy=None: _players(),
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
        lambda logger, page, max_pages, max_players=None, pacing_policy=None: _players(1),
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
        lambda logger, page, max_pages, max_players=None, pacing_policy=None: _players(1),
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


def test_value_incomplete_player_is_retried_once_after_main_pass(monkeypatch):
    calls = []
    payload_players = []
    errors = []

    def fake_detail_loop(logger, page, players, **kwargs):
        calls.append([player["slug"] for player in players])
        details = []
        value_rows = []
        for player in players:
            detail = {
                "player_name": player["name"],
                "team": "Athletic",
                "slug": player["slug"],
            }
            details.append(detail)
            if player.get("attempt") == "initial":
                kwargs["on_player_error"](
                    player=player,
                    stage="value_history_incomplete",
                    message="Value history incomplete: reason=csv_timeout matches=3 values=0",
                    details={"reason": "csv_timeout", "match_rows": 3, "value_rows": 0, "stats_rows": 1},
                )
                kwargs["on_player_payload"](
                    player=player,
                    detail_rows=[detail],
                    match_rows=[{"player_name": player["name"], "slug": player["slug"]}],
                    value_history_rows=[],
                    processed_count=len(details),
                )
            else:
                recovered_rows = [{"date": "2026-07-24", "market_value_eur": 1000000, "slug": player["slug"]}]
                value_rows.extend(recovered_rows)
                kwargs["on_player_payload"](
                    player=player,
                    detail_rows=[detail],
                    match_rows=[{"player_name": player["name"], "slug": player["slug"]}],
                    value_history_rows=recovered_rows,
                    processed_count=len(details),
                )
        return details, [], value_rows

    monkeypatch.setattr("scraping_biwenger.players.scrape.select_player_table_layout", lambda page, logger=None: None)
    monkeypatch.setattr(
        "scraping_biwenger.players.scrape.extract_all_player_names",
        lambda logger, page, max_pages, max_players=None, pacing_policy=None: _players(1),
    )
    monkeypatch.setattr("scraping_biwenger.players.scrape.scrape_all_players_detail", fake_detail_loop)

    _, detail_rows, _, value_rows = scrape_player_rows(
        object(),
        FakeLogger(),
        max_pages=1,
        max_players_detail=1,
        on_player_payload=lambda **kwargs: payload_players.append(kwargs["player"]),
        on_player_error=lambda **kwargs: errors.append(kwargs),
    )

    assert calls == [["player-1"], ["player-1"]]
    assert payload_players[1]["attempt"] == "value_retry"
    assert len(detail_rows) == 2
    assert len(value_rows) == 1
    assert errors[0]["stage"] == "value_history_incomplete"


def test_circuit_breaker_stops_main_pass_and_skips_retry_passes(monkeypatch):
    calls = []
    run_states = []

    def fake_detail_loop(logger, page, players, **kwargs):
        calls.append([player["slug"] for player in players])
        for idx, player in enumerate(players, start=1):
            kwargs["on_player_error"](
                player={**player, "rank": idx},
                stage="select_scoring_system",
                message="Points tab did not load usable content",
            )
            kwargs["on_player_event"](
                "player_failed",
                player_name=player["name"],
                player_slug=player["slug"],
                rank=idx,
                stage="select_scoring_system",
                message="Points tab did not load usable content",
            )
            if kwargs["stop_requested"]():
                break
        return [], [], []

    monkeypatch.setattr("scraping_biwenger.players.scrape.select_player_table_layout", lambda page, logger=None: None)
    monkeypatch.setattr(
        "scraping_biwenger.players.scrape.extract_all_player_names",
        lambda logger, page, max_pages, max_players=None, pacing_policy=None: _players(10),
    )
    monkeypatch.setattr("scraping_biwenger.players.scrape.scrape_all_players_detail", fake_detail_loop)

    _, detail_rows, _, _ = scrape_player_rows(
        object(),
        FakeLogger(),
        max_pages=1,
        max_players_detail=10,
        retry_top_players=10,
        on_run_state=run_states.append,
    )

    assert calls == [
        [
            "player-1",
            "player-2",
            "player-3",
            "player-4",
            "player-5",
            "player-6",
            "player-7",
            "player-8",
            "player-9",
            "player-10",
        ]
    ]
    assert detail_rows == []
    assert run_states[-1]["termination_reason"] == "circuit_breaker"
    assert run_states[-1]["circuit_breaker_triggered"] is True


def test_targeted_player_slug_bypasses_pacing(monkeypatch):
    captured_profiles = []

    def fake_detail_loop(logger, page, players, **kwargs):
        captured_profiles.append(kwargs["pacing_policy"].profile)
        return [], [], []

    monkeypatch.setattr("scraping_biwenger.players.scrape.scrape_all_players_detail", fake_detail_loop)

    scrape_player_rows(
        object(),
        FakeLogger(),
        player_slug="kazunari-kita",
        pacing_profile="slow",
    )

    assert captured_profiles == ["off"]


def test_value_retry_failure_is_recorded_once_without_loop(monkeypatch):
    calls = []
    errors = []

    def fake_detail_loop(logger, page, players, **kwargs):
        calls.append([player["attempt"] for player in players])
        detail = {
            "player_name": players[0]["name"],
            "team": "Athletic",
            "slug": players[0]["slug"],
        }
        kwargs["on_player_error"](
            player=players[0],
            stage="value_history_incomplete",
            message="Value history incomplete: reason=csv_timeout matches=3 values=0",
            details={"reason": "csv_timeout", "match_rows": 3, "value_rows": 0, "stats_rows": 1},
        )
        kwargs["on_player_payload"](
            player=players[0],
            detail_rows=[detail],
            match_rows=[{"player_name": players[0]["name"], "slug": players[0]["slug"]}],
            value_history_rows=[],
            processed_count=1,
        )
        return [detail], [], []

    monkeypatch.setattr("scraping_biwenger.players.scrape.select_player_table_layout", lambda page, logger=None: None)
    monkeypatch.setattr(
        "scraping_biwenger.players.scrape.extract_all_player_names",
        lambda logger, page, max_pages, max_players=None, pacing_policy=None: _players(1),
    )
    monkeypatch.setattr("scraping_biwenger.players.scrape.scrape_all_players_detail", fake_detail_loop)

    scrape_player_rows(
        object(),
        FakeLogger(),
        max_pages=1,
        max_players_detail=1,
        on_player_payload=lambda **kwargs: None,
        on_player_error=lambda **kwargs: errors.append(kwargs),
    )

    assert calls == [["initial"], ["value_retry"]]
    assert len(errors) == 2
    assert errors[0]["player"]["attempt"] == "initial"
    assert errors[1]["player"]["attempt"] == "value_retry"


def test_retry_pass_reuses_main_pacing_policy(monkeypatch):
    pacing_ids = []

    def fake_detail_loop(logger, page, players, **kwargs):
        pacing_ids.append(id(kwargs["pacing_policy"]))
        if players[0].get("attempt") == "initial":
            kwargs["on_player_error"](
                player=players[0],
                stage="select_scoring_system",
                message="Timeout waiting for scoring menu",
            )
            return [], [], []
        detail = {
            "player_name": players[0]["name"],
            "team": "Athletic",
            "slug": players[0]["slug"],
        }
        return [detail], [], []

    monkeypatch.setattr("scraping_biwenger.players.scrape.select_player_table_layout", lambda page, logger=None: None)
    monkeypatch.setattr(
        "scraping_biwenger.players.scrape.extract_all_player_names",
        lambda logger, page, max_pages, max_players=None, pacing_policy=None: _players(1),
    )
    monkeypatch.setattr("scraping_biwenger.players.scrape.scrape_all_players_detail", fake_detail_loop)

    scrape_player_rows(
        object(),
        FakeLogger(),
        max_pages=1,
        max_players_detail=1,
        retry_top_players=1,
        pacing_profile="human",
    )

    assert len(pacing_ids) == 2
    assert pacing_ids[0] == pacing_ids[1]


def test_value_retry_pass_reuses_main_pacing_policy(monkeypatch):
    pacing_ids = []

    def fake_detail_loop(logger, page, players, **kwargs):
        pacing_ids.append(id(kwargs["pacing_policy"]))
        detail = {
            "player_name": players[0]["name"],
            "team": "Athletic",
            "slug": players[0]["slug"],
        }
        if players[0].get("attempt") == "initial":
            kwargs["on_player_error"](
                player=players[0],
                stage="value_history_incomplete",
                message="Value history incomplete: reason=csv_timeout matches=3 values=0",
                details={"reason": "csv_timeout", "match_rows": 3, "value_rows": 0, "stats_rows": 1},
            )
            return [detail], [], []
        return [detail], [], [{"date": "2026-07-24", "market_value_eur": 1000000, "slug": players[0]["slug"]}]

    monkeypatch.setattr("scraping_biwenger.players.scrape.select_player_table_layout", lambda page, logger=None: None)
    monkeypatch.setattr(
        "scraping_biwenger.players.scrape.extract_all_player_names",
        lambda logger, page, max_pages, max_players=None, pacing_policy=None: _players(1),
    )
    monkeypatch.setattr("scraping_biwenger.players.scrape.scrape_all_players_detail", fake_detail_loop)

    scrape_player_rows(
        object(),
        FakeLogger(),
        max_pages=1,
        max_players_detail=1,
        pacing_profile="human",
    )

    assert len(pacing_ids) == 2
    assert pacing_ids[0] == pacing_ids[1]
