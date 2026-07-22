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


def test_open_player_via_search_recovered_fallback_logs_warning_not_exception(monkeypatch):
    logger = FakeLogger()
    page = FakePage()
    player = {"name": "Marc Roca", "slug": "marc-roca", "href": "/la-liga/players/marc-roca"}

    monkeypatch.setattr(
        search_and_open,
        "focus_and_clear_search_box",
        lambda page, timeout_ms=5000: (_ for _ in ()).throw(RuntimeError("search input timeout")),
    )
    monkeypatch.setattr(search_and_open, "wait_player_detail_loaded", lambda page, timeout_ms=8000: True)
    monkeypatch.setattr(search_and_open, "_log_timing", lambda *args, **kwargs: None)

    opened = search_and_open.open_player_via_search(logger, page, player)

    assert opened is True
    assert page.gotos == [("https://biwenger.as.com/la-liga/players/marc-roca", "domcontentloaded")]
    assert ("exception", "Error in open_player_via_search for 'Marc Roca': search input timeout") not in logger.records
    assert any(level == "warning" and "Search-path open failed for 'Marc Roca'" in message for level, message in logger.records)
    assert any(
        level == "info" and "Recovered player 'Marc Roca' via fallback href after search-path exception" in message
        for level, message in logger.records
    )


def test_open_player_via_search_failed_fallback_returns_false_without_exception_log(monkeypatch):
    logger = FakeLogger()
    page = FakePage()
    player = {"name": "Marc Roca", "slug": "marc-roca", "href": "/la-liga/players/marc-roca"}

    monkeypatch.setattr(
        search_and_open,
        "focus_and_clear_search_box",
        lambda page, timeout_ms=5000: (_ for _ in ()).throw(RuntimeError("search input timeout")),
    )
    monkeypatch.setattr(search_and_open, "wait_player_detail_loaded", lambda page, timeout_ms=8000: False)
    monkeypatch.setattr(search_and_open, "_log_timing", lambda *args, **kwargs: None)

    opened = search_and_open.open_player_via_search(logger, page, player)

    assert opened is False
    assert page.gotos == [("https://biwenger.as.com/la-liga/players/marc-roca", "domcontentloaded")]
    assert not any(level == "exception" for level, _ in logger.records)
    assert any(
        level == "warning" and "Fallback href did not load player detail in time for 'Marc Roca'" in message
        for level, message in logger.records
    )
