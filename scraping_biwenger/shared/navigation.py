import time

from scraping_biwenger.shared.config import DEFAULT_ROOT_URL
from scraping_biwenger.shared.timing import _log_timing


def click_tab_in_horizontal_main_menu(page, tab_name: str, logger=None):
    """
    Click a horizontal menu tab by name (case-insensitive).
    Examples: click_tab_in_horizontal_main_menu(page, "team")
    """
    target = tab_name.strip().lower()
    started_at = time.perf_counter()
    if logger:
        logger.info("Navigating to Biwenger tab: %s from %s", target, page.url)

    try:
        tab_selector = f'a[href="/{target}"]'
        page.locator(tab_selector).first.wait_for(state="visible", timeout=5000)
        page.click(tab_selector)
    except Exception:
        if logger:
            logger.info("Tab link for '%s' was not visible; navigating directly.", target)
        page.goto(f"{DEFAULT_ROOT_URL}{target}", wait_until="domcontentloaded")

    page.wait_for_url(f"**/{target}*", timeout=10000)
    _log_timing(logger, f"Landed on Biwenger tab: {target}", started_at)


def scroll_into_view(page, selector, hold=0.2):
    page.locator(selector).first.scroll_into_view_if_needed(timeout=2000)
    time.sleep(hold)  # Let rendering catch up
