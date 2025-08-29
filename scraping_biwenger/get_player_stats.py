from config_logging import get_logger
from scraping_biwenger.scraper_actions_in_biwenger import (
    load_biwenger_credentials,
    start_browser_accept_cookies,
    perform_login,
    click_tab_in_horizontal_main_menu,
    scroll_into_view
)
from supabase_client.connection import get_supabase_client
from supabase_client.utils import check_if_table_exists, insert_rows_into_table, upsert_rows_into_table, compute_content_hash

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
    season_label = _get_season_label(page)

    return {
        "player_name":     scrape_player_name(page) or "(unknown)",
        "team":            scrape_team_name(page)   or "",
        "position":        scrape_position(page)    or "",
        **scrape_player_status(page),
        **scrape_player_statistics(page),
        "season":          season_label or "",
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
        text = (btn.inner_text(timeout=timeout) or "").strip()
        return re.sub(r'\s*SEASON\s*', '', text, flags=re.IGNORECASE).strip()

    # Fallback: any button whose accessible name contains "season"
    try:
        btn2 = page.get_by_role("button", name=re.compile(r"season", re.I)).first
        text = (btn2.inner_text(timeout=timeout) or "").strip()
        return re.sub(r'\s*SEASON\s*', '', text, flags=re.IGNORECASE).strip()
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

def scrape_player_matches(page, logger=None) -> list[dict]:
    # Make sure the Points tab is visible, but don't blow up if it isn't
    try:
        open_points_tab(page)
    except Exception as e:
        if logger: logger.warning(f"⚠️ Points tab not available: {e}")
        return []

    # Try to get the table; if it's not there, just return []
    tbl = page.locator("player-detail-points point-list table").first
    try:
        tbl.wait_for(state="visible", timeout=8000)
    except Exception:
        if logger: logger.info("ℹ️ No per-match table visible for this player; skipping matches.")
        return []

    season_label = _get_season_label(page)

    rows = []
    try:
        tr_list = tbl.locator("tr")
        row_count = tr_list.count()  # ✅ no off-by-one
    except Exception:
        row_count = 0

    for i in range(row_count):
        tr = tr_list.nth(i)
        try:
            bar = tr.locator("td.bar-container a.bar")
            if bar.count() == 0:
                continue

            # Round label (e.g., R1)
            round_label = _safe_text(tr.locator('td.round a[title^="Round"]'))

            # Start datetime (ISO) -> date
            start_iso  = _safe_attr(tr.locator('meta[itemprop="startDate"]'), "content")
            match_date = _to_date_iso(start_iso) if start_iso else None

            # Points & Best XI — avoid locator.evaluate; read attributes/text safely
            bar_first = bar.first
            cls = (bar_first.get_attribute("class") or "")
            best_xi = "star" in cls
            points = _to_int(_safe_text(bar_first))

            # Events (join span@title)
            ev_spans = tr.locator("td.events player-events span")
            try:
                ev_count = ev_spans.count()
            except Exception:
                ev_count = 0
            titles = []
            for j in range(ev_count):
                t = _safe_attr(ev_spans.nth(j), "title")
                if t:
                    titles.append(t.strip())
            events_str = " | ".join(titles) if titles else ""

            if round_label:
                rows.append({
                    "season_label": season_label,
                    "round_label": round_label,
                    "match_date": match_date,
                    "points": points,
                    "best_xi": best_xi,
                    "events": events_str,
                })
        except Exception as e:
            if logger: logger.debug(f"row {i} parse failed: {e}")
            continue

    # De-dup season+round
    unique = {}
    for r in rows:
        if not r["round_label"]:
            continue
        unique[(r["season_label"], r["round_label"])] = r

    return list(unique.values())

def _is_on_detail(page) -> bool:
    """Heuristic: detail has player-detail-header or URL contains /players/."""
    try:
        if page.locator("player-detail-header h1").first.count() > 0:
            return True
    except Exception:
        pass
    return "/players/" in (page.url or "")

def _wait_for_list(page, timeout_ms: int = 10000) -> None:
    """Wait until the table view is visible."""
    page.wait_for_selector("table.table.no-swipe tbody tr th.text-left a", state="visible", timeout=timeout_ms)

def _ensure_on_list(page, timeout_ms: int = 10000) -> bool:
    """If currently in detail, go back until the list table is visible."""
    if not _is_on_detail(page):
        try:
            _wait_for_list(page, timeout_ms)
            return True
        except Exception:
            return False

    # we are on detail, go back once or twice (SPA sometimes pushes twice)
    for _ in range(2):
        try:
            page.go_back(wait_until="domcontentloaded", timeout=timeout_ms)
            try:
                _wait_for_list(page, timeout_ms)
                return True
            except Exception:
                # keep trying one more time
                continue
        except Exception:
            break
    return False

def _get_pagination_summary(page) -> str:
    """e.g., '1 - 9 of 504' / '10 - 18 of 504'"""
    try:
        return (page.locator("pagination span.summary").first.inner_text() or "").strip()
    except Exception:
        return ""

def click_next_list_page(page, timeout_ms: int = 10000) -> bool:
    """
    Click the '›' (next page) control in the table pagination.
    Returns True if the next page loads (summary text changes), else False.
    """
    try:
        _wait_for_list(page, timeout_ms)  # ensure we see the list
    except Exception:
        return False

    prev_summary = _get_pagination_summary(page)

    # Find an enabled '›' button
    next_btn = page.locator("pagination ul li:not(.disabled) a", has_text="›").first
    if next_btn.count() == 0:
        return False

    try:
        next_btn.scroll_into_view_if_needed()
        next_btn.click()
    except Exception:
        return False

    # Wait for the summary or the first row to change
    try:
        page.wait_for_function(
            """prev => {
                const s = document.querySelector('pagination span.summary');
                return s && s.textContent.trim() !== prev;
            }""",
            arg=prev_summary,
            timeout=timeout_ms
        )
    except Exception:
        # as a fallback, wait for any table re-render
        try:
            page.wait_for_load_state("networkidle", timeout=timeout_ms)
        except Exception:
            pass

    # Verify we actually moved
    curr_summary = _get_pagination_summary(page)
    return curr_summary and curr_summary != prev_summary

def iterate_all_players_sequential(
        page,
        max_players: int = 10000,
        logger=None) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Click first player, then:
      - scrape player snapshot
      - scrape matches
      - click Next (detail) until it disappears
      - when Next disappears (end of current table page), go back to the list,
        click '›' (next table page), click first player, and continue.
    """
    # Ensure we start from the list, then open the first player
    if not _ensure_on_list(page):
        raise RuntimeError("Could not reach the players list view to start iteration.")
    click_first_player(page)

    player_rows: List[Dict[str, Any]] = []
    match_rows:  List[Dict[str, Any]] = []
    seen_slugs: set[str] = set()  # de-dupe safety across pages

    for i in range(max_players):
        # Identify the current player robustly
        prev_url = page.url
        prev_name = scrape_player_name(page)
        # Try to extract slug from URL (works when detail changes the route)
        slug = ""
        m = re.search(r"/players/([^/?#]+)", prev_url or "")
        if m:
            slug = (m.group(1) or "").strip().lower()

        # Fallback identity: name + team from header
        team_name = scrape_team_name(page)
        name_norm = (prev_name or "").strip().lower()
        team_norm = (team_name or "").strip().lower()

        # Preferred key: slug; else composite (name|team)
        identity_key = slug if slug else f"{name_norm}|{team_norm}"

        if identity_key in seen_slugs:
            if logger:
                logger.info(f"↩️ Duplicate player detected, skipping: {prev_name} "
                            f"({'slug:' + slug if slug else f'name_team:{name_norm}|{team_norm}'})")
            # try to advance anyway to avoid getting stuck
        else:
            seen_slugs.add(identity_key)
            if logger:
                logger.info(f"🔍 Scraping player {i + 1}: {prev_name} "
                            f"({'slug:' + slug if slug else f'name_team:{name_norm}|{team_norm}'})")

            # --- scrape detail (1 row)
            detail = scrape_player_detail(page)
            detail["_seq"] = i + 1
            player_rows.append(detail)

            # --- scrape matches (N rows)
            try:
                # keep your current signature; this will work even if you haven’t
                # swapped in the resilient scrape_player_matches yet
                matches = scrape_player_matches(page)
            except Exception as e:
                if logger:
                    logger.warning(
                        f"⚠️ Failed to scrape matches for {detail.get('player_name', '(unknown)')}: {e}. Skipping matches."
                    )
                matches = []

            # enrich & append
            for mrow in matches:
                mrow["player_name"] = detail["player_name"]
                mrow["team"] = detail.get("team", "")
            match_rows.extend(matches)

            if logger and (i + 1) % 25 == 0:
                logger.info(f"…scraped {i + 1} players so far ({len(match_rows)} match rows).")

        # Try to move to the next player within the same table page
        if click_next_player_if_present(page, prev_url=prev_url, prev_name=prev_name):
            continue  # still in the same table page, keep going

        # No "Next" on detail (we're at the last row of this table page)
        if logger:
            logger.info("🧭 No detail 'Next' button; going back to list and clicking next table page…")

        # Go back to the list, click '›' to advance the pagination
        if not _ensure_on_list(page):
            if logger:
                logger.info("⚠️ Could not return to the list view. Stopping.")
            break

        if not click_next_list_page(page):
            if logger:
                logger.info("✔️ Reached the last table page (no enabled '›'). Stopping.")
            break

        # Open the first player in the new table page and keep going
        click_first_player(page)

    return player_rows, match_rows


def ETL_get_player_stats(max_players=10_000):
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
    try:
        perform_login(page, creds["email"], creds["password"])

        # 4) Navigate to players page
        click_tab_in_horizontal_main_menu(page, "players")

        # 5) Click view as list
        page.get_by_role("button", name="Table").click()

        # 6) Iterate over all players
        player_rows, match_rows = iterate_all_players_sequential(page, max_players=max_players, logger=logger)
        player_rows_pd = pd.DataFrame(player_rows)
        logger.info(f"✅ Scraped {player_rows_pd['player_name'].nunique()} players")

        match_rows_pd = pd.DataFrame(match_rows)
        logger.info(f"✅ Scraped {match_rows_pd['player_name'].nunique()} players")
        # print(match_rows_pd)

        page.pause()

        # 7) Save to Supabase
        supabase = get_supabase_client()
        table_name = "biwenger_player_stats"

        if not check_if_table_exists(supabase, table_name):
            logger.error(f"❌ Table '{table_name}' does not exist in Supabase.")
        else:
            if player_rows:
                _COMPARISON_COLS = [
                    "player_name", "team", "position", "status", "status_detail",
                    "points", "value", "min_value", "max_value", "matches_played", "average"
                ]

                # Optional: you don't *need* to send content_hash if the DB has a generated column,
                # but including it is fine and can help with debugging.
                for r in player_rows:
                    r["content_hash"] = compute_content_hash(r, _COMPARISON_COLS)

                # print(pd.DataFrame(player_rows))

                upsert_rows_into_table(
                    supabase,
                    table_name=table_name,
                    rows=player_rows,
                    on_conflict="content_hash"
                )
                logger.info(f"✅ Upserted {len(player_rows)} rows into '{table_name}' via content_hash.")
            else:
                logger.info("⏩ No player rows to insert.")

        table_name = "biwenger_player_matches"

        if not check_if_table_exists(supabase, table_name):
            logger.error(f"❌ Table '{table_name}' does not exist in Supabase.")
        else:
            if match_rows:
                # Delete everything first (truncate semantics)
                supabase.table(table_name).delete().neq("id", 0).execute()
                logger.info(f"🗑️ Cleared existing rows from '{table_name}'")

                # Insert fresh rows
                insert_rows_into_table(supabase, table_name=table_name, rows=match_rows)
                logger.info(f"✅ Inserted {len(match_rows)} rows into '{table_name}'")
            else:
                logger.info("⏩ No player rows to insert.")
    finally:
        try:
            context.close()
        except Exception:
            pass
        try:
            browser.close()
        except Exception:
            pass
        try:
            pw.stop()
        except Exception:
            pass

if __name__ == "__main__":
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)
    pd.set_option('display.max_colwidth', None)

    ETL_get_player_stats(max_players=25)
