from scraping_biwenger.players import search_and_open


class FakeLogger:
    def __init__(self):
        self.records = []

    def debug(self, msg, *args):
        self.records.append(("debug", msg % args if args else msg))

    def info(self, msg, *args):
        self.records.append(("info", msg % args if args else msg))

    def warning(self, msg, *args):
        self.records.append(("warning", msg % args if args else msg))

    def exception(self, msg, *args):
        self.records.append(("exception", msg % args if args else msg))


class FakePage:
    def __init__(self):
        self.gotos = []

    def goto(self, url, wait_until=None):
        self.gotos.append((url, wait_until))


def test_open_player_detail_uses_href_first_without_search_fallback(monkeypatch):
    logger = FakeLogger()
    page = FakePage()
    player = {"name": "Marc Roca", "slug": "marc-roca", "href": "/la-liga/players/marc-roca"}

    search_calls = []
    monkeypatch.setattr(search_and_open, "wait_player_detail_loaded", lambda page, timeout_ms=8000: True)
    monkeypatch.setattr(
        search_and_open,
        "open_player_via_search_only",
        lambda logger, page, player, base_url="https://biwenger.as.com": search_calls.append(player),
    )
    monkeypatch.setattr(search_and_open, "_log_timing", lambda *args, **kwargs: None)

    opened = search_and_open.open_player_detail(logger, page, player)

    assert opened is True
    assert page.gotos == [("https://biwenger.as.com/la-liga/players/marc-roca", "domcontentloaded")]
    assert search_calls == []


def test_open_player_detail_recovers_with_search_after_href_failure(monkeypatch):
    logger = FakeLogger()
    page = FakePage()
    player = {"name": "Marc Roca", "slug": "marc-roca", "href": "/la-liga/players/marc-roca"}

    monkeypatch.setattr(search_and_open, "wait_player_detail_loaded", lambda page, timeout_ms=8000: False)
    monkeypatch.setattr(
        search_and_open,
        "open_player_via_search_only",
        lambda logger, page, player, base_url="https://biwenger.as.com": True,
    )
    monkeypatch.setattr(search_and_open, "_log_timing", lambda *args, **kwargs: None)

    opened = search_and_open.open_player_detail(logger, page, player)

    assert opened is True
    assert page.gotos == [("https://biwenger.as.com/la-liga/players/marc-roca", "domcontentloaded")]
    assert any(
        level == "warning" and "Direct href open failed for 'Marc Roca'. Falling back to search flow." in message
        for level, message in logger.records
    )
    assert any(
        level == "info" and "Recovered player 'Marc Roca' via search fallback after direct href failure." in message
        for level, message in logger.records
    )


def test_open_player_detail_returns_false_when_href_and_search_fail(monkeypatch):
    logger = FakeLogger()
    page = FakePage()
    player = {"name": "Marc Roca", "slug": "marc-roca", "href": "/la-liga/players/marc-roca"}

    monkeypatch.setattr(search_and_open, "wait_player_detail_loaded", lambda page, timeout_ms=8000: False)
    monkeypatch.setattr(
        search_and_open,
        "open_player_via_search_only",
        lambda logger, page, player, base_url="https://biwenger.as.com": False,
    )
    monkeypatch.setattr(search_and_open, "_log_timing", lambda *args, **kwargs: None)

    opened = search_and_open.open_player_detail(logger, page, player)

    assert opened is False
    assert page.gotos == [("https://biwenger.as.com/la-liga/players/marc-roca", "domcontentloaded")]


def test_open_player_detail_direct_only_does_not_fall_back_to_search(monkeypatch):
    logger = FakeLogger()
    page = FakePage()
    player = {
        "name": "Marc Roca",
        "slug": "marc-roca",
        "href": "/la-liga/players/marc-roca",
        "open_by_href_only": True,
    }

    search_calls = []
    monkeypatch.setattr(search_and_open, "wait_player_detail_loaded", lambda page, timeout_ms=8000: False)
    monkeypatch.setattr(
        search_and_open,
        "open_player_via_search_only",
        lambda logger, page, player, base_url="https://biwenger.as.com": search_calls.append(player),
    )
    monkeypatch.setattr(search_and_open, "_log_timing", lambda *args, **kwargs: None)

    opened = search_and_open.open_player_detail(logger, page, player)

    assert opened is False
    assert page.gotos == [("https://biwenger.as.com/la-liga/players/marc-roca", "domcontentloaded")]
    assert search_calls == []
