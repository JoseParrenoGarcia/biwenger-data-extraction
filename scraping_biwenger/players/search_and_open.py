import random
import time
from typing import Dict

from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PWTimeout

from scraping_biwenger.shared.timing import _rand_sleep, log_timing_debug

# search and select pointers
SEARCH_INPUT_SEL = "player-filter input[placeholder='Search player']"
PLAYER_ROW_ANCHORS_SEL = "table.table.no-swipe tbody tr th[scope='row'] a"
PLAYER_DETAIL_READY_SEL = "player-detail-stats"

# going back to main page pointers
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


def _log_timing(logger, label: str, started_at: float, *, player_slug: str = "") -> None:
    log_timing_debug(logger, label, started_at, player_slug=player_slug)


def _open_player_via_href(
    logger,
    page: Page,
    *,
    name: str,
    slug: str,
    href: str,
    base_url: str,
    timing_label: str,
    success_log: str,
) -> bool:
    started_at = time.time()
    page.goto(base_url + href, wait_until="domcontentloaded")
    ok = wait_player_detail_loaded(page, timeout_ms=8000)
    _log_timing(logger, timing_label, started_at, player_slug=slug)
    if ok:
        logger.info(success_log, name, href)
        return True
    logger.warning("Fallback href did not load player detail in time for '%s': %s", name, href)
    return False


def open_player_via_search(
    logger, page: Page, player: Dict[str, str], base_url: str = "https://biwenger.as.com"
) -> bool:
    """
    Try to open a player's detail page via the search box.
    Falls back to href navigation if the search path fails.
    Returns True if player detail seems loaded.
    """
    name = (player.get("name") or "").strip()
    slug = (player.get("slug") or "").strip()
    href = player.get("href") or ""
    if not name:
        logger.warning("open_player_via_search: missing player name; skipping.")
        return False

    flow_started_at = time.time()
    if player.get("open_by_href_only") and href:
        try:
            if _open_player_via_href(
                logger,
                page,
                name=name,
                slug=slug,
                href=href,
                base_url=base_url,
                timing_label="Player direct href open",
                success_log="Opened player '%s' via direct href: %s",
            ):
                _log_timing(logger, "Player open flow", flow_started_at, player_slug=slug)
                return True
            return False
        except Exception as e:
            logger.exception(f"Error opening direct href for '{name}': {e}")
            return False

    try:
        # 1) Focus + clear search
        step_started_at = time.time()
        focus_and_clear_search_box(page)
        _log_timing(logger, "Player search clear input", step_started_at, player_slug=slug)
        # 2) Type name
        step_started_at = time.time()
        type_player_name(page, name)
        _log_timing(logger, "Player search type query", step_started_at, player_slug=slug)
        # 3) Wait table filtered
        step_started_at = time.time()
        if not wait_table_filtered_for_name(page, name, timeout_ms=7000):
            _log_timing(logger, "Player search filter wait failed", step_started_at, player_slug=slug)
            logger.warning(f"Search didn't show expected results for '{name}'. Trying fallback to href if available.")
            if href:
                if _open_player_via_href(
                    logger,
                    page,
                    name=name,
                    slug=slug,
                    href=href,
                    base_url=base_url,
                    timing_label="Player fallback href open",
                    success_log="Recovered player '%s' via fallback href after search mismatch: %s",
                ):
                    _log_timing(logger, "Player open flow", flow_started_at, player_slug=slug)
                    return True
                return False
            return False
        _log_timing(logger, "Player search filter wait", step_started_at, player_slug=slug)

        # 4) Click a matching row
        step_started_at = time.time()
        clicked = click_matching_player_row(page, name)
        _log_timing(logger, "Player search result click", step_started_at, player_slug=slug)
        if not clicked:
            logger.warning(f"Couldn't click a result row for '{name}'.")
            # fallback to href
            if href:
                if _open_player_via_href(
                    logger,
                    page,
                    name=name,
                    slug=slug,
                    href=href,
                    base_url=base_url,
                    timing_label="Player fallback href open",
                    success_log="Recovered player '%s' via fallback href after row-click miss: %s",
                ):
                    _log_timing(logger, "Player open flow", flow_started_at, player_slug=slug)
                    return True
            return False

        # 5) Wait for player detail
        step_started_at = time.time()
        if not wait_player_detail_loaded(page, timeout_ms=9000):
            _log_timing(logger, "Player detail wait failed", step_started_at, player_slug=slug)
            logger.warning(f"Player detail didn't appear after clicking result for '{name}'. Attempting href fallback.")
            if href:
                if _open_player_via_href(
                    logger,
                    page,
                    name=name,
                    slug=slug,
                    href=href,
                    base_url=base_url,
                    timing_label="Player fallback href open after click",
                    success_log="Recovered player '%s' via fallback href after detail wait miss: %s",
                ):
                    _log_timing(logger, "Player open flow", flow_started_at, player_slug=slug)
                    return True
            return False
        _log_timing(logger, "Player detail wait", step_started_at, player_slug=slug)

        logger.debug("Player detail opened via search: %s", name)
        _log_timing(logger, "Player open flow", flow_started_at, player_slug=slug)
        return True

    except Exception as e:
        logger.warning("Search-path open failed for '%s': %s. Trying fallback href if available.", name, e)
        # Last-chance fallback
        if href:
            try:
                if _open_player_via_href(
                    logger,
                    page,
                    name=name,
                    slug=slug,
                    href=href,
                    base_url=base_url,
                    timing_label="Player fallback href open after exception",
                    success_log="Recovered player '%s' via fallback href after search-path exception: %s",
                ):
                    _log_timing(logger, "Player open flow", flow_started_at, player_slug=slug)
                    return True
            except Exception as fallback_error:
                logger.warning("Fallback href also failed for '%s': %s", name, fallback_error)
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


def _clear_search_box_when_ready(page: Page, timeout_ms: int = 1200) -> None:
    try:
        page.wait_for_selector(SEARCH_INPUT_SEL, timeout=timeout_ms, state="visible")
    except PWTimeout:
        return
    clear_search_box_if_present(page)


def click_back_to_players_table(page: Page, timeout_ms: int = 3500) -> bool:
    """
    Click the arrow-back in the player detail header to return to the table.
    Fallback to go_back() / reload if needed. Waits for player-list anchors
    and clears search when the search box is ready.
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
        page.wait_for_selector(PLAYER_ROW_ANCHORS_SEL, timeout=timeout_ms)
        _clear_search_box_when_ready(page)
        return True

    except PWTimeout:
        # Last fallback: hard reload; then try waiting again
        try:
            page.reload(wait_until="domcontentloaded")
            page.wait_for_selector(PLAYER_ROW_ANCHORS_SEL, timeout=timeout_ms)
            _clear_search_box_when_ready(page)
            return True
        except Exception:
            return False
    except Exception:
        return False
