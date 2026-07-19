import time

from playwright.sync_api import sync_playwright

from scraping_biwenger.shared.auth import accept_cookies_if_present
from scraping_biwenger.shared.config import DEFAULT_ROOT_URL
from scraping_biwenger.shared.timing import _log_timing


def start_browser_accept_cookies(headless: bool = True, logger=None):
    """
    Start browser, accept cookies (if present), log in, land on app page.
    Returns (pw, browser, context, page).
    """
    started_at = time.perf_counter()
    if logger:
        logger.info("Starting Chromium browser. headless=%s", headless)
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=headless, args=["--disable-gpu", "--no-sandbox"])
    context = browser.new_context(accept_downloads=True)
    page = context.new_page()
    page.set_default_timeout(15000)
    page.set_default_navigation_timeout(20000)
    _log_timing(logger, "Browser context ready", started_at)

    started_at = time.perf_counter()
    if logger:
        logger.info("Navigating to Biwenger main page: %s", DEFAULT_ROOT_URL)
    page.goto(DEFAULT_ROOT_URL)
    _log_timing(logger, "Landed on Biwenger main page", started_at)
    accept_cookies_if_present(page, logger=logger)
    return pw, browser, context, page
