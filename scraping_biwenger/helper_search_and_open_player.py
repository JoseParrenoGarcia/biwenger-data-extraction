from playwright.sync_api import Page, TimeoutError as PWTimeout
from typing import Dict
from scraping_biwenger.utils import _rand_sleep
import random
import time

# search and select pointers
SEARCH_INPUT_SEL = "player-filter input[placeholder='Search player']"
PLAYER_ROW_ANCHORS_SEL = "table.table.no-swipe tbody tr th[scope='row'] a"
PLAYER_DETAIL_READY_SEL = "player-detail-stats"

# going back to main page pointers
PLAYER_TABLE_ROWS_SEL = "table.table.no-swipe tbody tr"
BACK_CONTAINER_SEL = "div.header .container[role='button'][aria-label='Close']"
BACK_ICON_SEL = "div.header i.icon.icon-arrow-left"


def focus_and_clear_search_box(page: Page, timeout_ms: int = 5000) -> None:
    page.wait_for_selector(SEARCH_INPUT_SEL, timeout=timeout_ms)
    inp = page.locator(SEARCH_INPUT_SEL)
    inp.click()
    # Clear any existing value:
    # 1) triple-click to select all
    inp.click(click_count=3)
    # 2) Backspace a few times to be safe
    for _ in range(5):
        inp.press("Backspace")
    _rand_sleep(0.1, 0.25)

def type_player_name(page: Page, name: str) -> None:
    inp = page.locator(SEARCH_INPUT_SEL)
    inp.type(name, delay=random.uniform(20, 60))  # human-ish typing
    _rand_sleep(0.15, 0.3)

def wait_table_filtered_for_name(page: Page, name: str, timeout_ms: int = 6000) -> bool:
    """
    Wait until the table rows reflect the filter.
    Returns True if at least one row appears and the first anchor looks relevant.
    """
    start = time.time()
    name_low = name.strip().lower()
    while (time.time() - start) * 1000 < timeout_ms:
        rows = page.locator(PLAYER_ROW_ANCHORS_SEL)
        count = rows.count()
        if count > 0:
            first_text = rows.first.inner_text().strip()
            # heuristic: first row contains the query (case-insensitive) or exact match
            if name_low in first_text.lower() or first_text.lower() == name_low:
                return True
            # Even if first isn't exact, we still have results—good enough to click exact match if present
            for i in range(min(count, 10)):
                if rows.nth(i).inner_text().strip().lower() == name_low:
                    return True
        _rand_sleep(0.1, 0.25)
    return False

def click_matching_player_row(page: Page, name: str) -> bool:
    """
    Prefer exact name match (case-insensitive) among the visible rows; otherwise click first row.
    Returns True if clicked.
    """
    rows = page.locator(PLAYER_ROW_ANCHORS_SEL)
    n = rows.count()
    if n == 0:
        return False

    target_idx = 0
    name_low = name.strip().lower()
    for i in range(n):
        txt = rows.nth(i).inner_text().strip()
        if txt.lower() == name_low:
            target_idx = i
            break
    rows.nth(target_idx).click()
    return True

def wait_player_detail_loaded(page: Page, timeout_ms: int = 8000) -> bool:
    try:
        page.wait_for_selector(PLAYER_DETAIL_READY_SEL, timeout=timeout_ms)
        return True
    except PWTimeout:
        return False

def open_player_via_search(logger, page: Page, player: Dict[str, str], base_url: str = "https://biwenger.as.com") -> bool:
    """
    Try to open a player's detail page via the search box.
    Falls back to href navigation if the search path fails.
    Returns True if player detail seems loaded.
    """
    name = (player.get("name") or "").strip()
    href = player.get("href") or ""
    if not name:
        logger.warning("open_player_via_search: missing player name; skipping.")
        return False

    try:
        # 1) Focus + clear search
        focus_and_clear_search_box(page)
        # 2) Type name
        type_player_name(page, name)
        # 3) Wait table filtered
        if not wait_table_filtered_for_name(page, name, timeout_ms=7000):
            logger.warning(f"Search didn't show expected results for '{name}'. Trying fallback to href if available.")
            if href:
                page.goto(base_url + href, wait_until="domcontentloaded")
                ok = wait_player_detail_loaded(page, timeout_ms=8000)
                if ok:
                    logger.info(f"✅ Opened via fallback href: {href}")
                    return True
                logger.warning("Fallback href did not load player detail in time.")
                return False
            return False

        # 4) Click a matching row
        clicked = click_matching_player_row(page, name)
        if not clicked:
            logger.warning(f"Couldn't click a result row for '{name}'.")
            # fallback to href
            if href:
                page.goto(base_url + href, wait_until="domcontentloaded")
                ok = wait_player_detail_loaded(page, timeout_ms=8000)
                if ok:
                    logger.info(f"✅ Opened via fallback href: {href}")
                    return True
            return False

        # 5) Wait for player detail
        if not wait_player_detail_loaded(page, timeout_ms=9000):
            logger.warning(f"Player detail didn't appear after clicking result for '{name}'. Attempting href fallback.")
            if href:
                page.goto(base_url + href, wait_until="domcontentloaded")
                ok = wait_player_detail_loaded(page, timeout_ms=8000)
                if ok:
                    logger.info(f"✅ Opened via fallback href after click: {href}")
                    return True
            return False

        logger.info(f"🟢 Player detail opened via search: {name}")
        return True

    except Exception as e:
        logger.exception(f"Error in open_player_via_search for '{name}': {e}")
        # Last-chance fallback
        if href:
            try:
                page.goto(base_url + href, wait_until="domcontentloaded")
                if wait_player_detail_loaded(page, timeout_ms=8000):
                    logger.info(f"✅ Opened via fallback href after exception: {href}")
                    return True
            except Exception:
                pass
        return False

def clear_search_box_if_present(page: Page) -> None:
    """
    Safe no-op if the search input isn’t visible yet. Leaves the table unchanged,
    just clears any prior query so the next search has full rows.
    """
    loc = page.locator(SEARCH_INPUT_SEL)
    if loc.count() == 0:
        return
    try:
        loc.first.click()
        loc.first.click(click_count=3)
        for _ in range(6):
            loc.first.press("Backspace")
        _rand_sleep(0.1, 0.25)
    except Exception:
        pass

def click_back_to_players_table(page: Page, timeout_ms: int = 8000) -> bool:
    """
    Click the arrow-back in the player detail header to return to the table.
    Fallback to go_back() / reload if needed. Waits until table & search reappear.
    """
    try:
        # Prefer the container with role=button (larger hitbox)
        if page.locator(BACK_CONTAINER_SEL).count() > 0:
            page.locator(BACK_CONTAINER_SEL).first.click()
        elif page.locator(BACK_ICON_SEL).count() > 0:
            page.locator(BACK_ICON_SEL).first.click()
        else:
            # SPA fallback
            page.go_back(wait_until="domcontentloaded")

        # Wait until we are back on the table view
        page.wait_for_selector(PLAYER_TABLE_ROWS_SEL, timeout=timeout_ms)
        page.wait_for_selector(SEARCH_INPUT_SEL, timeout=timeout_ms)
        clear_search_box_if_present(page)
        return True

    except PWTimeout:
        # Last fallback: hard reload; then try waiting again
        try:
            page.reload(wait_until="domcontentloaded")
            page.wait_for_selector(PLAYER_TABLE_ROWS_SEL, timeout=timeout_ms)
            page.wait_for_selector(SEARCH_INPUT_SEL, timeout=timeout_ms)
            clear_search_box_if_present(page)
            return True
        except Exception:
            return False
    except Exception:
        return False
