import time
from typing import Dict, List, Optional

from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PWTimeout

from scraping_biwenger.players.network_telemetry import network_action
from scraping_biwenger.players.pacing import PlayerRunPacingPolicy
from scraping_biwenger.shared.auth import dismiss_app_popups_if_present
from scraping_biwenger.shared.timing import _rand_sleep

PAGINATION_UL_SEL = "pagination ul"
NEXT_LI_SEL = "pagination ul li:has-text('›')"
PLAYER_ANCHORS_SEL = "table.table.no-swipe tbody tr th[scope='row'] a"


def is_next_enabled(page: Page) -> bool:
    """
    Returns True if the '›' pagination control exists and is NOT disabled.
    From your HTML:
      - First page: prev controls are 'disabled'
      - Last page: next ('›') and last ('»') have class 'disabled'
    """
    try:
        page.wait_for_selector(PAGINATION_UL_SEL, timeout=5000)
    except PWTimeout:
        return False

    li = page.locator(NEXT_LI_SEL)
    if li.count() == 0:
        # No next control in DOM
        return False

    classes = (li.first.get_attribute("class") or "").strip()
    return "disabled" not in classes


def click_next_if_enabled(page: Page) -> bool:
    """
    Clicks '›' if enabled. Returns True if clicked, False otherwise.
    """
    if not is_next_enabled(page):
        return False
    # Click the <a> inside that LI
    with network_action(page, "paginate_players"):
        page.locator(f"{NEXT_LI_SEL} a").first.click()
    return True


def get_first_row_key(page: Page) -> Optional[str]:
    """
    Returns a stable key (prefer href/slug; fallback to text) for the first row,
    so we can detect page changes after clicking next.
    """
    try:
        page.wait_for_selector(PLAYER_ANCHORS_SEL, timeout=8000)
    except PWTimeout:
        return None

    first = page.locator(PLAYER_ANCHORS_SEL).first
    if first.count() == 0:
        return None

    href = first.get_attribute("href")
    if href:
        return href
    text = first.inner_text().strip()
    return text or None


def wait_for_table_change(page: Page, previous_first_key: Optional[str], timeout_ms: int = 10000) -> None:
    """
    Spin-wait until the first-row key changes (Angular re-render done).
    """
    start = time.time()
    while (time.time() - start) * 1000 < timeout_ms:
        key = get_first_row_key(page)
        if key and key != previous_first_key:
            return
        _rand_sleep(0.12, 0.3)
    # If no change, let the caller decide what to do next.


def extract_players_from_current_table(page: Page) -> List[Dict[str, str]]:
    """
    Extract {name, slug, href} for the current table page.
    You can extend later (team, pos, points, etc.).
    """
    page.wait_for_selector(PLAYER_ANCHORS_SEL, timeout=8000)
    anchors = page.locator(PLAYER_ANCHORS_SEL)
    n = anchors.count()
    out: List[Dict[str, str]] = []
    for i in range(n):
        a = anchors.nth(i)
        name = a.inner_text().strip()
        href = a.get_attribute("href") or ""
        slug = href.rstrip("/").split("/")[-1] if href else ""
        out.append({"name": name, "slug": slug, "href": href})
    return out


def extract_all_player_names(
    logger,
    page: Page,
    max_pages: Optional[int] = None,
    max_players: Optional[int] = None,
    pacing_policy: Optional[PlayerRunPacingPolicy] = None,
) -> List[Dict[str, str]]:
    """
    Iterate the players table by clicking '›' until it becomes disabled (last page),
    or until `max_pages` pages have been processed / `max_players` unique players
    have been collected. Extracts {name, slug, href} per row and returns a
    de-duplicated list (by slug, else by (name, href)).

    Args:
        logger: your configured logger
        page: Playwright Page already on the Players table view
        max_pages: optional cap on number of pages to process (1-based). If None, runs to the end.
        max_players: optional cap on number of unique players to collect.

    Returns:
        List[Dict[str, str]] with keys: name, slug, href
    """
    players_all: List[Dict[str, str]] = []
    seen = set()
    pacing_policy = pacing_policy or PlayerRunPacingPolicy(profile="off", enabled=False)

    try:
        page_idx = 1
        # small initial wait to make sure table is ready
        try:
            page.wait_for_selector("table.table.no-swipe tbody tr", timeout=8000)
        except PWTimeout:
            dismissed = dismiss_app_popups_if_present(page, logger=logger)
            if dismissed and logger:
                logger.info("Retrying player table wait after dismissing app pop-up.")
            page.wait_for_selector("table.table.no-swipe tbody tr", timeout=8000)

        while True:
            # Extract on current page
            players = extract_players_from_current_table(page)
            added = 0
            for p in players:
                if max_players is not None and len(players_all) >= max_players:
                    break
                key = p.get("slug") or (p.get("name"), p.get("href"))
                if key not in seen:
                    players_all.append(p)
                    seen.add(key)
                    added += 1
            logger.info(f"🧾 Page {page_idx}: got {len(players)} rows, +{added} new (total {len(players_all)}).")

            if max_players is not None and len(players_all) >= max_players:
                logger.info(f"⛔ Reached max_players={max_players}. Pagination discovery stopping early.")
                break

            # Stop after max_pages if requested
            if max_pages is not None and page_idx >= max_pages:
                logger.info(f"⛔ Reached max_pages={max_pages}. Stopping early.")
                break

            # Try to go next; if not enabled, we're done
            previous_first = get_first_row_key(page)
            pacing_policy.apply("before_paginate", processed=len(players_all))
            if not click_next_if_enabled(page):
                logger.info("✅ 'Next' is disabled (last page). Pagination finished.")
                break

            # Wait for a real table change
            wait_for_table_change(page, previous_first, timeout_ms=12_000)
            pacing_policy.apply("after_paginate", processed=len(players_all))
            _rand_sleep(0.4, 0.9)
            page_idx += 1

        logger.info(f"✅ Finished pagination with {len(players_all)} unique players.")
        return players_all

    except Exception as e:
        logger.exception(f"Error during pagination loop: {e}")
        # Always return a list (empty on failure) so ETL flow can decide what to do next
        return []
