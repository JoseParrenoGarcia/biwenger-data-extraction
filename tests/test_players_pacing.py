from scraping_biwenger.players import discover, pacing


class FakeLogger:
    def __init__(self):
        self.debug_messages = []
        self.info_messages = []
        self.exception_messages = []

    def debug(self, *args):
        self.debug_messages.append(args)

    def info(self, *args):
        self.info_messages.append(args)

    def exception(self, *args):
        self.exception_messages.append(args)


class RecordingPolicy:
    def __init__(self):
        self.calls = []

    def apply(self, point: str, *, processed: int = 0) -> None:
        self.calls.append((point, processed))


class FakePage:
    def wait_for_selector(self, selector, timeout=0):
        return None


def test_build_pacing_policy_human_default_logs_delay(monkeypatch):
    logger = FakeLogger()
    policy = pacing.build_pacing_policy("", logger=logger)

    monkeypatch.setattr(pacing, "uniform", lambda start, end: (start + end) / 2)
    monkeypatch.setattr(pacing, "sleep", lambda delay: None)

    policy.apply("after_open", processed=7)

    assert policy.profile == "human"
    assert logger.debug_messages
    assert logger.debug_messages[-1][0].startswith("PACING point=%s")
    assert logger.debug_messages[-1][1:] == ("after_open", "human", 7, 2.9)


def test_targeted_player_bypasses_pacing():
    policy = pacing.build_pacing_policy("human", targeted_player=True)

    assert policy.profile == "off"
    assert policy.enabled is False


def test_extract_all_player_names_applies_pagination_pacing(monkeypatch):
    logger = FakeLogger()
    policy = RecordingPolicy()
    page = FakePage()
    pages = [
        [{"name": "A", "slug": "a", "href": "/la-liga/players/a"}],
        [{"name": "B", "slug": "b", "href": "/la-liga/players/b"}],
    ]
    state = {"idx": 0}

    monkeypatch.setattr(discover, "extract_players_from_current_table", lambda page: pages[state["idx"]])
    monkeypatch.setattr(discover, "get_first_row_key", lambda page: f"page-{state['idx']}")
    monkeypatch.setattr(discover, "wait_for_table_change", lambda page, previous_first_key, timeout_ms=10000: None)
    monkeypatch.setattr(discover, "_rand_sleep", lambda a=0.25, b=1.5: None)

    def fake_click_next(page):
        if state["idx"] == 0:
            state["idx"] = 1
            return True
        return False

    monkeypatch.setattr(discover, "click_next_if_enabled", fake_click_next)

    players = discover.extract_all_player_names(
        logger=logger,
        page=page,
        max_pages=3,
        pacing_policy=policy,
    )

    assert [player["slug"] for player in players] == ["a", "b"]
    assert policy.calls == [
        ("before_paginate", 1),
        ("after_paginate", 1),
        ("before_paginate", 2),
    ]
