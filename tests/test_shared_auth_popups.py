from playwright.sync_api import TimeoutError as PWTimeout

from scraping_biwenger.shared.auth import dismiss_app_popups_if_present


class FakeLogger:
    def __init__(self):
        self.info_messages = []
        self.warning_messages = []
        self.debug_messages = []

    def info(self, message, *args):
        self.info_messages.append(message % args if args else message)

    def warning(self, message, *args):
        self.warning_messages.append(message % args if args else message)

    def debug(self, message, *args):
        self.debug_messages.append(message % args if args else message)


class FakeLocator:
    def __init__(self, *, can_click):
        self.can_click = can_click
        self.clicked = False

    @property
    def first(self):
        return self

    def click(self, timeout):
        if not self.can_click:
            raise RuntimeError("not clickable")
        self.clicked = True


class FakePopupPage:
    def __init__(self, *, has_dialog=True, clickable_selector="button.close-button"):
        self.has_dialog = has_dialog
        self.clickable_selector = clickable_selector
        self.locators = {}

    def wait_for_selector(self, selector, timeout, state):
        if state == "visible" and not self.has_dialog:
            raise PWTimeout("no dialog")
        if state == "detached":
            return None
        return None

    def locator(self, selector):
        can_click = self.clickable_selector in selector
        locator = FakeLocator(can_click=can_click)
        self.locators[selector] = locator
        return locator


def test_dismiss_app_popups_if_present_closes_visible_dialog():
    logger = FakeLogger()
    page = FakePopupPage()

    dismissed = dismiss_app_popups_if_present(page, logger=logger)

    assert dismissed is True
    assert logger.info_messages == [
        "Dismissed Biwenger app pop-up with selector ng-component[role='dialog'][aria-modal='true'] button.close-button."
    ]


def test_dismiss_app_popups_if_present_is_false_when_absent():
    logger = FakeLogger()
    page = FakePopupPage(has_dialog=False)

    dismissed = dismiss_app_popups_if_present(page, logger=logger)

    assert dismissed is False
    assert logger.debug_messages == ["No Biwenger app pop-up detected."]
