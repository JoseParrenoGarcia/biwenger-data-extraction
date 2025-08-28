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
from typing import Dict, Any, List, Callable, Tuple
import re
import json
from datetime import date, datetime

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

def _safe_text(l, timeout=2000):
    try:
        return l.inner_text(timeout=timeout).strip()
    except Exception:
        return ""

def _safe_attr(l, name, timeout=2000):
    try:
        return l.get_attribute(name, timeout=timeout)
    except Exception:
        return None

def _to_int(s):
    try:
        return int(str(s).replace("–", "-").replace("−", "-").strip())
    except Exception:
        return 0

def _to_date_iso(date_str):
    """Input like 2025-08-24T19:30:00.000Z -> 2025-08-24"""
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00")).date().isoformat()
    except Exception:
        return None

def _get_season_label(page, timeout=3000) -> str:
    # Prefer the explicit attribute in your markup
    btn = page.locator('player-detail-points .section.light button[modalmenutitle="Season"]').first
    if btn.count():
        return (btn.inner_text(timeout=timeout) or "").strip()

    # Fallback: any button whose accessible name contains “season”
    try:
        btn2 = page.get_by_role("button", name=re.compile(r"season", re.I)).first
        return (btn2.inner_text(timeout=timeout) or "").strip()
    except Exception:
        return ""

def open_points_tab(page, timeout=10000):
    """
    Ensure the right-hand 'Points' tab is active and loaded.
    Click the tab header (not the tabpanel) and wait for the table to appear.
    """
    # If it's already visible, bail early
    if page.locator("player-detail-points point-list table").first.count() > 0:
        return

    # Scroll the tab header area into view (some UIs lazy-load on scroll)
    try:
        page.locator("linear-tabs").first.scroll_into_view_if_needed()
    except Exception:
        pass

    # Try clickable headers by ARIA role first
    clicked = False
    try:
        page.get_by_role("tab", name=re.compile(r"^Points$", re.I)).click()
        clicked = True
    except Exception:
        # Fallbacks: various header list selectors
        for sel in (
            "linear-tabs ul li:has-text('Points') a",
            "linear-tabs ul li:has-text('Points')",
            "tab[header='Points'] ~ *",  # last-ditch: click sibling header area if present
        ):
            loc = page.locator(sel).first
            if loc.count():
                try:
                    loc.scroll_into_view_if_needed()
                    loc.click()
                    clicked = True
                    break
                except Exception:
                    continue

    # If we didn’t click anything (maybe already selected), continue to wait anyway
    try:
        page.wait_for_selector("player-detail-points point-list table, player-detail-points .section.light:has-text('Total')",
                               timeout=timeout, state="visible")
    except PWTimeout:
        # Surface a clearer error for debugging
        raise RuntimeError("Points tab did not load its table. Is the header click targeting the right element?")

def scrape_player_matches(page) -> list[dict]:
    open_points_tab(page)

    # Wait for the table to exist; don’t assume first row has a bar
    page.wait_for_selector("player-detail-points point-list table", timeout=10000)
    tr_list = page.locator("player-detail-points point-list table tr")

    season_label = _get_season_label(page)

    rows = []
    for i in range(tr_list.count()+1):
        tr = tr_list.nth(i)
        bar = tr.locator("td.bar-container a.bar")
        if bar.count() == 0:
            continue

        # Round label (e.g., R1)
        round_a = tr.locator('td.round a[title^="Round"]')
        round_label = _safe_text(round_a)

        # Start datetime (ISO) -> date
        start_iso = _safe_attr(tr.locator('meta[itemprop="startDate"]'), "content")
        match_date = _to_date_iso(start_iso) if start_iso else None

        # Points & Best XI
        best_xi = bar.first.evaluate("el => el.classList.contains('star')") if bar.count() else False
        points = _to_int(_safe_text(bar.first))

        # Events: grab span@title values, join into one string
        ev_spans = tr.locator("td.events player-events span")
        titles = []
        for j in range(ev_spans.count()):
            t = _safe_attr(ev_spans.nth(j), "title")
            if t:
                titles.append(t.strip())

        events_str = " | ".join(titles) if titles else ""

        rows.append({
            "season_label": season_label,
            "round_label": round_label,
            "match_date": match_date,
            "points": points,
            "best_xi": best_xi,
            "events": events_str,
        })

    # remove duplicates based on season+round_label, excluding null round_label
    unique = {}
    for r in rows:
        # Skip rows where round_label is null/empty
        if not r["round_label"]:
            continue
        key = (r["season_label"], r["round_label"])
        unique[key] = r  # keeps the last occurrence

    rows = list(unique.values())

    return rows

def iterate_all_players_sequential(
        page,
        max_players: int = 10000,
        logger=None) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Click first player, then for each player:
      - scrape player snapshot
      - scrape match rows
      - click Next until it disappears
    Returns (player_rows, match_rows)
    """
    click_first_player(page)

    player_rows: List[Dict[str, Any]] = []
    match_rows:  List[Dict[str, Any]] = []

    for i in range(max_players):
        # capture stable identity before scraping/next
        prev_url  = page.url
        prev_name = scrape_player_name(page)

        logger.info(f"🔍 Scraping player {i + 1}: {prev_name}")

        # --- scrape detail (1 row)
        detail = scrape_player_detail(page)
        detail["_seq"] = i + 1
        player_rows.append(detail)

        # --- scrape matches (N rows)
        matches = scrape_player_matches(page)
        # enrich match rows with player identifiers for easy joins
        for m in matches:
            m["player_name"] = detail["player_name"]
            m["team"] = detail.get("team", "")
        match_rows.extend(matches)

        if logger and (i + 1) % 25 == 0:
            logger.info(f"…scraped {i+1} players so far ({len(match_rows)} match rows).")

        # advance
        if not click_next_player_if_present(page, prev_url=prev_url, prev_name=prev_name):
            if logger:
                logger.info("Reached the last player (no Next button).")
            break

    return player_rows, match_rows



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
    player_rows, match_rows = iterate_all_players_sequential(page, max_players=10, logger=logger)
    player_rows_pd = pd.DataFrame(player_rows)
    logger.info(f"✅ Scraped {player_rows_pd['player_name'].nunique()} players")

    match_rows_pd = pd.DataFrame(match_rows)
    logger.info(f"✅ Scraped {match_rows_pd['player_name'].nunique()} players")
    # print(match_rows_pd)

    # 7) Save to Supabase
    supabase = get_supabase_client()
    table_name = "biwenger_player_stats"

    if not check_if_table_exists(supabase, table_name):
        logger.error(f"❌ Table '{table_name}' does not exist in Supabase.")
    else:
        if player_rows:
            insert_rows_into_table(supabase, table_name=table_name, rows=player_rows)
            logger.info(f"✅ Inserted {len(player_rows)} rows into '{table_name}'")
        else:
            logger.info("⏩ No player rows to insert.")

    table_name = "biwenger_player_matches"

    if not check_if_table_exists(supabase, table_name):
        logger.error(f"❌ Table '{table_name}' does not exist in Supabase.")
    else:
        if match_rows:
            # insert_rows_into_table(supabase, table_name=table_name, rows=match_rows)
            # logger.info(f"✅ Inserted {len(match_rows)} rows into '{table_name}'")

            # Delete everything first (truncate semantics)
            supabase.table(table_name).delete().neq("id", 0).execute()
            logger.info(f"🗑️ Cleared existing rows from '{table_name}'")

            # Insert fresh rows
            insert_rows_into_table(supabase, table_name=table_name, rows=match_rows)
            logger.info(f"✅ Inserted {len(match_rows)} rows into '{table_name}'")
        else:
            logger.info("⏩ No player rows to insert.")


    page.pause()

if __name__ == "__main__":
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)
    pd.set_option('display.max_colwidth', None)

    ETL_get_player_stats()
