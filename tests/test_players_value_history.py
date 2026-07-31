from contextlib import nullcontext

from playwright.sync_api import TimeoutError as PWTimeout

from scraping_biwenger.players import value_history


class FakeLocator:
    def __init__(self, name: str, *, count: int = 1, visible: bool = True):
        self.name = name
        self._count = count
        self.visible = visible
        self.clicked = 0
        self.scrolled = 0

    @property
    def first(self):
        return self

    def count(self):
        return self._count

    def filter(self, **_kwargs):
        return self

    def scroll_into_view_if_needed(self):
        self.scrolled += 1

    def click(self):
        self.clicked += 1

    def wait_for(self, state="visible", timeout=0):
        if state == "visible" and not self.visible:
            raise PWTimeout(f"{self.name} not visible within {timeout}ms")


class FakePage:
    def __init__(self, locators: dict[str, FakeLocator], role_tab_locator: FakeLocator | None = None):
        self.locators = locators
        self.role_tab_locator = role_tab_locator or FakeLocator("role_tab", count=0, visible=False)

    def locator(self, selector: str):
        return self.locators.get(selector, FakeLocator(selector, count=0, visible=False))

    def get_by_role(self, role: str, name=None):
        if role == "tab":
            return self.role_tab_locator
        return FakeLocator(f"{role}:{name}", count=0, visible=False)


def test_open_value_tab_prefers_clickable_tab_header_and_waits_for_tools(monkeypatch):
    clickable_tab = FakeLocator("clickable_value_tab", count=1, visible=True)
    hidden_panel_like = FakeLocator("hidden_panel", count=0, visible=False)
    page = FakePage(
        {
            value_history.VALUE_TAB: clickable_tab,
            value_history.VALUE_PANEL: FakeLocator("value_panel", count=1, visible=False),
            value_history.CHART_SURFACE: FakeLocator("chart_surface", count=1, visible=False),
            value_history.TOOLS: FakeLocator("tools", count=1, visible=True),
            value_history.CSV_BTN: FakeLocator("csv_btn", count=1, visible=False),
            "[role='tabpanel']": hidden_panel_like,
        }
    )
    monkeypatch.setattr(value_history, "network_action", lambda *args, **kwargs: nullcontext())

    assert value_history.open_value_tab(page, timeout=3000) is True
    assert clickable_tab.clicked == 1
    assert clickable_tab.scrolled == 1


def test_open_value_tab_returns_false_when_no_ready_selector_appears(monkeypatch):
    clickable_tab = FakeLocator("clickable_value_tab", count=1, visible=True)
    page = FakePage(
        {
            value_history.VALUE_TAB: clickable_tab,
            value_history.VALUE_PANEL: FakeLocator("value_panel", count=1, visible=False),
            value_history.CHART_SURFACE: FakeLocator("chart_surface", count=1, visible=False),
            value_history.TOOLS: FakeLocator("tools", count=1, visible=False),
            value_history.CSV_BTN: FakeLocator("csv_btn", count=1, visible=False),
            "player-detail-price": FakeLocator("player_detail_price", count=1, visible=False),
            "value-chart": FakeLocator("value_chart", count=1, visible=False),
            "price-history": FakeLocator("price_history", count=1, visible=False),
            "[role='tabpanel']": FakeLocator("hidden_panel", count=0, visible=False),
        }
    )
    monkeypatch.setattr(value_history, "network_action", lambda *args, **kwargs: nullcontext())

    assert value_history.open_value_tab(page, timeout=3000) is False


def test_open_value_tab_accepts_svg_chart_panel_ready_state(monkeypatch):
    page = FakePage(
        {
            value_history.VALUE_PANEL: FakeLocator("value_panel", count=1, visible=True),
            value_history.TOOLS: FakeLocator("tools", count=1, visible=False),
            value_history.CSV_BTN: FakeLocator("csv_btn", count=1, visible=False),
            value_history.CHART_SURFACE: FakeLocator("chart_surface", count=1, visible=True),
            "player-detail-price": FakeLocator("player_detail_price", count=1, visible=True),
        }
    )
    monkeypatch.setattr(value_history, "network_action", lambda *args, **kwargs: nullcontext())

    assert value_history.open_value_tab(page, timeout=3000) is True
