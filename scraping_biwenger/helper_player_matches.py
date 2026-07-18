from __future__ import annotations

from typing import Callable, Optional, List, Dict
from playwright.sync_api import Page, TimeoutError as PWTimeout
import re
import time
import random
from datetime import datetime

# -----------------------------
# Small safe helpers
# -----------------------------

def _safe_text(locator) -> str:
    try:
        txt = locator.inner_text()
        return re.sub(r"\s+", " ", (txt or "")).strip()
    except Exception:
        return ""

def _safe_attr(locator, name: str) -> str:
    try:
        val = locator.get_attribute(name)
        return (val or "").strip()
    except Exception:
        return ""

def _to_int(text: str) -> int:
    if not text:
        return 0
    s = text.replace("\u2212", "-")
    s = re.sub(r"[^\d\-]", "", s)
    try:
        return int(s) if s not in ("", "-", "--") else 0
    except Exception:
        return 0

def _to_date_iso(iso_str: str) -> Optional[str]:
    """
    Convert startDate ISO string (e.g., '2025-09-14T14:15:00.000Z') to 'YYYY-MM-DD'.
    Returns None if parsing fails.
    """
    if not iso_str:
        return None
    try:
        # Accept both '...Z' and timezone-less forms
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.date().isoformat()
    except Exception:
        # Last-ditch: keep only the first 10 chars if they look like a date
        m = re.match(r"(\d{4}-\d{2}-\d{2})", iso_str)
        return m.group(1) if m else None

def _get_season_label(page: Page) -> str:
    """
    Return the currently selected Points-tab season label.

    Prefer the visible Biwenger season button, e.g. "2025/2026 season", because
    the URL can contain stale or app-level season hints that do not match the
    match rows currently rendered.
    """
    # Best source: the visible season selector in the player points panel.
    selectors = [
        'player-detail-points button[modalmenutitle="Season"]',
        'button[modalmenutitle="Season"]',
    ]
    for selector in selectors:
        try:
            button = page.locator(selector).first
            if button.count() > 0:
                text = _safe_text(button)
                normalized = re.sub(r"\s*season\s*$", "", text, flags=re.IGNORECASE).strip()
                if normalized:
                    return normalized
        except Exception:
            pass

    # Try URL param
    try:
        m = re.search(r"[?&]season=(20\d{2}-20\d{2})", page.url)
        if m:
            return m.group(1).replace("-", "/")
    except Exception:
        pass
    # Try any nearby link containing season pattern (very defensive)
    try:
        link = page.locator("a[href*='20'][href*='-20']").first
        if link.count() > 0:
            m = re.search(r"(20\d{2}-20\d{2})", _safe_attr(link, "href"))
            if m:
                return m.group(1).replace("-", "/")
    except Exception:
        pass
    return ""

# -----------------------------
# UI: open the "Points" tab
# -----------------------------

def _log_timing(logger, label: str, started_at: float) -> None:
    if logger:
        logger.info("%s completed in %.2fs", label, time.time() - started_at)


def open_points_tab(page: Page, timeout: int = 10_000, logger=None):
    """
    Ensure the right-hand 'Points' tab is active and loaded.
    Click the tab header (not the tabpanel) and wait for the table or 'Total' block.
    Safe to call if already active.
    """
    started_at = time.time()
    # Already visible?
    if page.locator("player-detail-points point-list table").first.count() > 0:
        _log_timing(logger, "Points tab already visible check", started_at)
        return

    # Scroll tab header area into view (in case of lazy-load)
    try:
        page.locator("linear-tabs").first.scroll_into_view_if_needed()
    except Exception:
        pass

    clicked = False
    # Prefer ARIA role=tab
    try:
        page.get_by_role("tab", name=re.compile(r"^Points$", re.I)).click()
        clicked = True
    except Exception:
        # Fallback selectors
        for sel in (
            "linear-tabs ul li:has-text('Points') a",
            "linear-tabs ul li:has-text('Points')",
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

    # Even if we didn't click (maybe already selected), wait for content
    try:
        page.wait_for_selector(
            "player-detail-points point-list table, player-detail-points .section.light:has-text('Total')",
            timeout=timeout,
            state="visible",
        )
        _log_timing(logger, "Points tab open/wait", started_at)
    except PWTimeout:
        _log_timing(logger, "Points tab open/wait failed", started_at)
        raise RuntimeError(
            "Points tab did not load its table. Verify the header selector and that the tab is present."
        )


def _normalize_scoring_system_label(label: str) -> str:
    normalized = re.sub(r"\s+", " ", (label or "").strip()).lower()
    if normalized == "sofascore":
        return "sofascore"
    return normalized.replace(" ", "_").replace(".", "")


def select_scoring_system(
    page: Page,
    *,
    target_label: str = "SofaScore",
    timeout: int = 10_000,
    logger=None,
) -> str:
    """
    Select the desired player points scoring system and return its normalized key.
    """
    started_at = time.time()
    open_points_tab(page, timeout=timeout, logger=logger)

    button_selector = 'player-detail-points score-selector-btn button[modalmenutitle="Scoring system"]'
    fallback_selector = 'button[modalmenutitle="Scoring system"]'

    button = page.locator(button_selector).first
    if button.count() == 0:
        button = page.locator(fallback_selector).first

    current_label = _safe_text(button)
    target_key = _normalize_scoring_system_label(target_label)
    if _normalize_scoring_system_label(current_label) == target_key:
        if logger:
            logger.info("Scoring system already selected: %s", current_label)
        _log_timing(logger, "Scoring system selection", started_at)
        return target_key

    button.click(timeout=timeout)
    page.wait_for_selector("round-league-score-menu", timeout=timeout, state="visible")

    option = page.locator("round-league-score-menu button").filter(
        has_text=re.compile(rf"^\s*{re.escape(target_label)}\s*$", re.I)
    ).first
    option.click(timeout=timeout)

    page.wait_for_function(
        """
        ({ selector, fallbackSelector, target }) => {
            const button =
                document.querySelector(selector) ||
                document.querySelector(fallbackSelector);
            return button && (button.textContent || '').trim().toLowerCase() === target.toLowerCase();
        }
        """,
        arg={
            "selector": button_selector,
            "fallbackSelector": fallback_selector,
            "target": target_label,
        },
        timeout=timeout,
    )
    page.wait_for_selector("player-detail-points point-list table", timeout=timeout, state="visible")

    if logger:
        logger.info("Selected scoring system: %s", target_label)
    _log_timing(logger, "Scoring system selection", started_at)
    return target_key

# -----------------------------
# Scrape per-match rows
# -----------------------------

def scrape_player_matches(page: Page, logger=None) -> List[Dict]:
    """
    Extract per-match rows from the 'Points' tab.
    Returns list of dicts (one per round), or [] if not available.
    Dict keys:
      - season_label, round_label, match_date (YYYY-MM-DD)
      - points (int), best_xi (bool), events (str)
    """
    # Ensure Points tab is visible
    try:
        open_points_tab(page, logger=logger)
    except Exception as e:
        if logger: logger.warning(f"⚠️ Points tab not available: {e}")
        return []

    # Get the table; if it's not there, just return []
    tbl = page.locator("player-detail-points point-list table").first
    try:
        tbl.wait_for(state="visible", timeout=8000)
    except Exception:
        if logger: logger.info("ℹ️ No per-match table visible for this player; skipping matches.")
        return []

    season_label = _get_season_label(page)

    rows: List[Dict] = []
    try:
        tr_list = tbl.locator("tr")
        row_count = tr_list.count()
    except Exception:
        row_count = 0

    for i in range(row_count):
        tr = tr_list.nth(i)
        try:
            bar = tr.locator("td.bar-container a.bar")
            if bar.count() == 0:
                continue

            # Round label (e.g., "R1")
            round_label = _safe_text(tr.locator('td.round a[title^="Round"]'))

            # Start datetime (ISO) -> date
            start_iso  = _safe_attr(tr.locator('meta[itemprop="startDate"]'), "content")
            match_date = _to_date_iso(start_iso) if start_iso else None

            # Points & Best XI (class contains 'star' when in best XI)
            bar_first = bar.first
            cls = (_safe_attr(bar_first, "class") or "")
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

    # De-dupe season+round (keep last seen)
    unique = {}
    for r in rows:
        if not r["round_label"]:
            continue
        unique[(r["season_label"], r["round_label"])] = r

    return list(unique.values())

# -----------------------------
# Simple retry helper
# -----------------------------

def with_retries(
    fn: Callable[[], Optional[object]],
    validate: Callable[[object], bool] = lambda x: True,
    attempts: int = 3,
    base_sleep: float = 0.5,
    logger=None,
):
    """
    Retry `fn()` a few times with exponential backoff until `validate(result)` is True.
    Returns the last successful result (even if it fails validation on final try),
    or None if all attempts raise.
    """
    last = None
    last_err = None
    for k in range(attempts):
        try:
            last = fn()
            if validate(last):
                return last
            if logger: logger.debug(f"retry {k+1}/{attempts}: validation failed; backing off…")
        except Exception as e:
            last_err = e
            if logger: logger.debug(f"retry {k+1}/{attempts}: exception {e}; backing off…")
        time.sleep(base_sleep * (1.5 ** k) + random.random() * 0.2)

    if logger and last_err:
        logger.warning(f"Gave up after {attempts} attempts. Last error: {last_err}")
    return last
