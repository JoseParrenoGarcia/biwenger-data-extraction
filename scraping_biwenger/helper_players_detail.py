from typing import Dict, Optional
from playwright.sync_api import Page
import re

# -----------------------------
# Small parsing helpers
# -----------------------------

def _parse_int(text: str) -> Optional[int]:
    if not text:
        return None
    s = text.replace("\u2212", "-")
    s = re.sub(r"[^\d\-]", "", s)
    try:
        return int(s) if s not in ("", "-", "--") else None
    except Exception:
        return None

def _parse_float(text: str) -> Optional[float]:
    if not text:
        return None
    s = text.replace("\u2212", "-")
    s = re.sub(r"[^\d\.\-]", "", s)
    try:
        return float(s) if s not in ("", "-", "--", ".") else None
    except Exception:
        return None

def _parse_money(text: str) -> Optional[int]:
    # "€23,020,000" -> 23020000
    if not text:
        return None
    s = text.replace("\u2212", "-")
    s = re.sub(r"[^\d\-]", "", s)
    try:
        return int(s) if s not in ("", "-", "--") else None
    except Exception:
        return None

# -----------------------------
# Header fields
# -----------------------------

def scrape_player_name(page: Page, timeout_ms: int = 6000) -> str:
    """
    Return the player's name from the detail view.
    Primary source: <player-detail-header> h1
    Fallbacks: generic h1, then URL slug (/players/<slug>).
    """
    # 1) best selector
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

    # 3) fallback from URL
    try:
        m = re.search(r"/players/([^/?#]+)", page.url)
        if m:
            slug = m.group(1)
            name = slug.replace("-", " ").strip()
            if name:
                return name
    except Exception:
        pass

    return ""

def scrape_team_name(page: Page, timeout_ms: int = 6000) -> str:
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

def scrape_position(page: Page, timeout_ms: int = 6000) -> str:
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

# -----------------------------
# Status
# -----------------------------

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

    if "icon-ok" in cls or "success" in cls or re.search(r"\bfit\b", t):
        return "fit"

    return "unknown"

def scrape_player_status(page: Page, timeout_ms: int = 4000) -> Dict[str, Optional[str]]:
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

# -----------------------------
# Statistics panel (minimal)
# -----------------------------

def scrape_player_statistics(page, timeout_ms: int = 6000) -> dict:
    """
    Extract key statistics from the Statistics panel on the player detail page.
    Returns ints/floats for numeric fields, defaults to 0 if unavailable.
    """
    stats = {
        "points": 0,
        "value": 0,
        "min_value": 0,
        "max_value": 0,
        "matches_played": 0,
        "average": 0.0,
    }

    try:
        page.wait_for_selector("player-detail-stats", timeout=timeout_ms)
    except Exception:
        return stats

    # Points
    try:
        pts = (
            page.locator("player-detail-stats .stat", has_text="Points")
            .locator("div")
            .first.inner_text()
            .strip()
        )
        stats["points"] = _parse_int(pts)
    except Exception:
        pass

    # Value
    try:
        val = page.locator("player-detail-stats tr", has_text="Value").locator("td.tr").inner_text()
        stats["value"] = _parse_money(val)
    except Exception:
        pass

    # Matches Played
    try:
        mp = (
            page.locator("player-detail-stats .stat", has_text="Matches")
            .locator("div")
            .first.inner_text()
            .strip()
        )
        stats["matches_played"] = _parse_int(mp)
    except Exception:
        pass

    # Average
    try:
        avg = (
            page.locator("player-detail-stats .stat", has_text="Average")
            .locator("div")
            .first.inner_text()
            .strip()
        )
        stats["average"] = float(avg.replace(",", "."))
    except Exception:
        # Fallback: compute average if possible, else keep 0.0
        if stats["matches_played"] > 0:
            stats["average"] = round(stats["points"] / stats["matches_played"], 1)
        else:
            stats["average"] = 0.0

    return stats

# -----------------------------
# Season label (minimal, optional)
# -----------------------------

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

# -----------------------------
# Composer
# -----------------------------

def scrape_player_detail(page: Page) -> Dict:
    season_label = _get_season_label(page)

    return {
        "player_name":     scrape_player_name(page) or "(unknown)",
        "team":            scrape_team_name(page)   or "",
        "position":        scrape_position(page)    or "",
        **scrape_player_status(page),
        **scrape_player_statistics(page),
        "season":          season_label or "",
    }
