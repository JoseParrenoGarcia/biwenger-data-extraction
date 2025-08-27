from config_logging import get_logger
from scraping_biwenger.scraper_actions_in_biwenger import (
    load_biwenger_credentials,
    start_browser_accept_cookies,
    perform_login,
    click_tab_in_horizontal_main_menu,
    scroll_into_view
)
from supabase_client.connection import get_supabase_client
from supabase_client.utils import check_if_table_exists, insert_rows_into_table

import pandas as pd
from playwright.sync_api import TimeoutError as PWTimeout
from typing import Dict, Any, List, Callable
import re

def click_first_player(page) -> None:
    first_link = page.locator("table.table.no-swipe tbody tr th.text-left a").first
    first_link.scroll_into_view_if_needed()
    first_link.click()
    page.wait_for_load_state("domcontentloaded")

def _next_player_locator(page):
    """
    Return a locator for the 'next player' control.
    """
    candidates = [
        "a.navigation.next",                       # clean, matches the HTML
        'a[role="button"].navigation.next',        # more explicit
        'a:has(.icon-chevron-right)',              # fallback
    ]
    for css in candidates:
        loc = page.locator(css).first
        if loc.count() > 0:
            return loc
    return page.locator("__no_match__")

def click_next_player_if_present(page, prev_url: str = "", prev_name: str = "", timeout_ms: int = 10000) -> bool:
    loc = _next_player_locator(page)
    if loc.count() == 0:
        return False
    try:
        loc.scroll_into_view_if_needed()
        loc.click()

        # Prefer URL change if they update /players/<slug>
        if "/players/" in page.url:
            page.wait_for_function(
                "prev => location.href !== prev",
                arg=prev_url or page.url,
                timeout=timeout_ms
            )
        else:
            # Fallback: wait until the H1 text changes
            page.wait_for_function(
                """prev => {
                    const h1 = document.querySelector('player-detail-header h1, h1');
                    return !!h1 && h1.textContent.trim() !== prev;
                }""",
                arg=(prev_name or ""),
                timeout=timeout_ms
            )

        # Give the UI a breath to hydrate
        page.wait_for_load_state("networkidle", timeout=timeout_ms)
        return True
    except Exception:
        return False

def scrape_player_name(page, timeout_ms: int = 6000) -> str:
    """
    Return the player's name from the detail view.
    Primary source: <player-detail-header> h1
    Fallbacks: generic h1, then URL slug (/players/<slug>).
    """
    # 1) best selector: the H1 inside the player-detail header
    try:
        page.wait_for_selector("player-detail-header h1", timeout=timeout_ms, state="visible")
        txt = page.locator("player-detail-header h1").first.inner_text()
        name = re.sub(r"\s+", " ", (txt or "").strip())
        if name:
            return name
    except Exception:
        pass

    # 2) generic H1 fallback
    try:
        txt = page.locator("h1").first.inner_text()
        name = re.sub(r"\s+", " ", (txt or "").strip())
        if name:
            return name
    except Exception:
        pass

    # 3) final fallback: derive from URL slug if present
    try:
        m = re.search(r"/players/([^/?#]+)", page.url)
        if m:
            slug = m.group(1)
            # Convert "ronald-araujo" -> "ronald araujo" (can’t recover accents)
            name = slug.replace("-", " ").strip()
            if name:
                return name
    except Exception:
        pass

    return ""

def scrape_team_name(page, timeout_ms: int = 6000) -> str:
    """
    From player-detail header: <team-link><a title="Real Madrid" href="...">
    Prefer the 'title' attribute; fallback to slug in href.
    """
    try:
        page.wait_for_selector("player-detail-header team-link a", timeout=timeout_ms, state="attached")
        link = page.locator("player-detail-header team-link a").first
        title = (link.get_attribute("title") or "").strip()
        if title:
            return title
        href = link.get_attribute("href") or ""
        m = re.search(r"/teams/([^/?#]+)", href)
        if m:
            return m.group(1).replace("-", " ").title()
    except Exception:
        pass
    return ""

def scrape_position(page, timeout_ms: int = 6000) -> str:
    """
    From header: <player-position title="Forward" aria-label="Forward">F</player-position>
    Prefer 'title' or 'aria-label'; fallback to the inner text (F/GK/D/M/etc).
    """
    try:
        page.wait_for_selector("player-detail-header player-position", timeout=timeout_ms, state="attached")
        pos = page.locator("player-detail-header player-position").first
        title = (pos.get_attribute("title") or pos.get_attribute("aria-label") or "").strip()
        if title:
            return title
        # fallback to single-letter content
        txt = (pos.inner_text() or "").strip()
        return txt
    except Exception:
        return ""

def _normalize_status_category(classes: str, text: str) -> str:
    """
    Map class names / text to a canonical category.
    """
    cls = (classes or "").lower()
    t = (text or "").lower()

    if "icon-injured" in cls or "injur" in t:
        return "injured"
    if "icon-doubt" in cls or "doubt" in t or "doubtful" in t:
        return "doubtful"
    if "icon-sanctioned" in cls or "suspend" in t or "sanction" in t or "red" in t:
        return "suspended"
    if "icon-discarded" in cls or "not in match squad" in t or "discard" in t:
        return "not_in_squad"

    # Some pages might render "icon-ok label success" (rare on detail); treat as fit.
    if "icon-ok" in cls or "success" in cls or re.search(r"\bfit\b", t):
        return "fit"

    return "unknown"

def scrape_player_status(page, timeout_ms: int = 4000) -> dict:
    """
    Returns:
        {
          "status": one of {"fit","injured","doubtful","suspended","not_in_squad","unknown"},
          "status_detail": full Biwenger text if available (else None)
        }
    """
    selectors = [
        "player-detail-header h1 player-status",
        "player-detail-info .tc player-status.with-label",
        "player-detail-info player-status",
    ]

    status_node = None
    for sel in selectors:
        loc = page.locator(sel)
        if loc.count() > 0:
            status_node = loc.first
            break

    if not status_node:
        return {"status": "fit", "status_detail": None}

    classes = (status_node.get_attribute("class") or "").strip()
    aria = (status_node.get_attribute("aria-label") or "").strip()
    title = (status_node.get_attribute("title") or "").strip()
    text = (status_node.inner_text().strip() if status_node.inner_text() else "")

    detail = aria or title or text or ""

    status = _normalize_status_category(classes, detail)

    return {
        "status": status,
        "status_detail": detail if detail else None,
    }

def _parse_int(text: str) -> int:
    if not text: return 0
    return int(re.sub(r"[^\d-]", "", text.replace("\u2212", "-")) or 0)

def _parse_float(text: str) -> float:
    if not text: return 0.0
    return float(re.sub(r"[^\d\.-]", "", text.replace("\u2212", "-")) or 0.0)

def _parse_money(text: str) -> int:
    # "€23,020,000" -> 23020000
    if not text: return 0
    return int(re.sub(r"[^\d-]", "", text.replace("\u2212", "-")) or 0)

def scrape_player_statistics(page, timeout_ms: int = 6000) -> dict:
    """
    Extract key statistics from the Statistics panel on the player detail page.
    Returns ints/floats for numeric fields.
    """
    stats = {
        "points": None,
        "value": None,
        "min_value": None,
        "max_value": None,
        "matches_played": None,
        "average": None,
    }

    try:
        page.wait_for_selector("player-detail-stats", timeout=timeout_ms)
    except Exception:
        return stats

    # Points
    try:
        pts = page.locator("player-detail-stats .stat", has_text="Points").locator("div").first.inner_text().strip()
        stats["points"] = _parse_int(pts)
    except Exception:
        pass

    # Value, Min, Max
    try:
        stats["value"] = _parse_money(page.locator("player-detail-stats tr", has_text="Value").locator("td.tr").inner_text())
    except Exception:
        pass
    try:
        stats["min_value"] = _parse_money(page.locator("player-detail-stats tr", has_text="Min").locator("td.tr").inner_text())
    except Exception:
        pass
    try:
        stats["max_value"] = _parse_money(page.locator("player-detail-stats tr", has_text="Max").locator("td.tr").inner_text())
    except Exception:
        pass

    # Matches played
    try:
        mp = page.locator("player-detail-stats .stat", has_text="Matches played").locator("div").first.inner_text().strip()
        stats["matches_played"] = _parse_int(mp)
    except Exception:
        pass

    # Average
    try:
        avg = page.locator("player-detail-stats .stat", has_text="Average").locator("div").first.inner_text().strip()
        stats["average"] = _parse_float(avg)
    except Exception:
        pass

    return stats

def scrape_player_detail(page) -> dict:
    return {
        "player_name":     scrape_player_name(page) or "(unknown)",
        "team":            scrape_team_name(page)   or "",
        "position":        scrape_position(page)    or "",
        **scrape_player_status(page),
        **scrape_player_statistics(page)
    }

def iterate_all_players_sequential(
    page,
    scrape_fn: Callable[[Any], Dict[str, Any]] = scrape_player_detail,
    max_players: int = 10000,
    logger=None,
) -> List[Dict[str, Any]]:
    """
    1) Click the first player in the table
    2) For each player: scrape with `scrape_fn`
    3) Click Next and wait until the player changes (URL or H1)
    """
    click_first_player(page)

    out: List[Dict[str, Any]] = []

    for i in range(max_players):
        # Capture current identifiers BEFORE clicking Next
        prev_url  = page.url
        prev_name = scrape_player_name(page)  # cheap + reliable anchor

        # Scrape full details for the CURRENT player
        row = scrape_fn(page)  # <-- pluggable parser
        row["_seq"] = i + 1
        out.append(row)

        if logger and (i + 1) % 25 == 0:
            logger.info(f"…scraped {i+1} players so far")

        # Try to move to the next player; wait until it actually changes
        if not click_next_player_if_present(page, prev_url=prev_url, prev_name=prev_name):
            if logger:
                logger.info("Reached the last player (no Next button).")
            break

    return out


def ETL_get_player_stats():
    """
    ETL: Login to Biwenger, scrape player stats, and (later) upload to Supabase.
    """
    logger = get_logger(
        "ETL_get_player_stats",
        log_file="logs/ETL_get_player_stats.log"
    )
    logger.info("=" * 70)
    logger.info("🚀 Starting ETL: get_player_stats")
    logger.info("=" * 70)

    # 1) Load credentials (from secrets/biwenger.toml)
    creds = load_biwenger_credentials()
    logger.info("✅ Credentials loaded successfully.")

    # 2) Start browser
    pw, browser, context, page = start_browser_accept_cookies(headless=True)
    logger.info("✅ Logged in")

    # 3) Login
    perform_login(page, creds["email"], creds["password"])

    # 4) Navigate to players page
    click_tab_in_horizontal_main_menu(page, "players")

    # 5) Click view as list
    page.get_by_role("button", name="Table").click()

    # 6) Iterate over all players
    rows = iterate_all_players_sequential(page, max_players=10, logger=logger)
    logger.info(f"✅ Scraped {len(rows)} players (stub).")
    print(pd.DataFrame(rows))

    page.pause()

if __name__ == "__main__":
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)
    pd.set_option('display.max_colwidth', None)

    ETL_get_player_stats()
