import re

import pandas as pd
from playwright.sync_api import TimeoutError as PWTimeout


def _to_int_generic(text: str) -> int:
    """Extract first integer in text like '  9  ' -> 9."""
    if text is None:
        return 0
    m = re.search(r"-?\d+", text.replace("\u2212", "-"))
    return int(m.group()) if m else 0


def _to_float_generic(text: str) -> float:
    """Extract first float-like number '4.5' from text."""
    if text is None:
        return 0.0
    m = re.search(r"-?\d+(?:\.\d+)?", text.replace("\u2212", "-"))
    return float(m.group()) if m else 0.0


def _to_int_money(text: str) -> int:
    """Convert '€2,370,000' -> 2370000; handles unicode minus and spaces."""
    if text is None:
        return 0

    t = (
        text.replace("€", "")
        .replace("\u2212", "-")
        .replace(",", "")
        .replace(".", "")
        .strip()
    )

    num_re = re.compile(r"[-\d]+")
    matches = num_re.findall(t)
    if not matches:
        return 0
    return int("".join(matches)) if t.startswith("-") else int("".join(matches))


def _mv_change_from_increment(row) -> int:
    """
    Return signed market-value change from a Biwenger increment/decrement element.
    """
    inc = row.locator("td.tr increment").first
    if inc.count() == 0:
        return 0
    text = (inc.get_attribute("aria-label") or inc.inner_text() or "").strip()
    cls = (inc.get_attribute("class") or "").lower()
    val = _to_int_money(text)
    if "decrement" in cls:
        return -abs(val)
    if "increment" in cls:
        return abs(val)
    return 0 if val == 0 else val


def _status_from_element(row) -> str:
    """
    Prefer explicit accessibility labels, then fall back to class hints.
    """
    el = row.locator("player-status").first
    if el.count() == 0:
        return "unknown"
    try:
        aria = el.get_attribute("aria-label") or el.get_attribute("title") or ""
        aria = aria.strip()
        if aria:
            if "Fit" in aria:
                return "fit"
            if "Injured" in aria:
                return "injured"
            if "Doubt" in aria or "Doubtful" in aria or "Questionable" in aria:
                return "doubt"
            return aria.lower()
    except Exception:
        pass

    try:
        cls = (el.get_attribute("class") or "").lower()
        if "success" in cls or "ok" in cls:
            return "fit"
        if "danger" in cls or "injured" in cls:
            return "injured"
        if "warning" in cls or "doubt" in cls or "question" in cls:
            return "doubt"
    except Exception:
        pass
    return "unknown"


def scrape_basic_team_table(page) -> pd.DataFrame:
    """
    Scrapes: name, points, market_value, mv_change_eur, status, GP, Avg, Form.
    """
    try:
        page.wait_for_selector("table.table.no-swipe tbody tr", timeout=8000, state="attached")
    except PWTimeout:
        return pd.DataFrame([])

    rows = page.locator("table.table.no-swipe tbody tr")
    data = []
    for i in range(rows.count()):
        row = rows.nth(i)

        try:
            name = row.locator("th.text-left a").first.inner_text().strip()
        except Exception:
            name = ""

        try:
            points_td = row.locator("th.text-left").locator("xpath=following-sibling::td[1]")
            points = _to_int_generic(points_td.inner_text())
        except Exception:
            points = 0

        try:
            market_value = _to_int_money(row.locator("td.tr").first.inner_text().strip())
        except Exception:
            market_value = 0

        mv_change_eur = _mv_change_from_increment(row)
        status = _status_from_element(row)

        try:
            status_td = row.locator("player-status").first.locator("xpath=..")
            gp_td = status_td.locator("xpath=following-sibling::td[1]")
            avg_td = status_td.locator("xpath=following-sibling::td[2]")
            gp = _to_int_generic(gp_td.inner_text())
            avg = _to_float_generic(avg_td.inner_text())
        except Exception:
            gp, avg = 0, 0.0

        try:
            form_cells = row.locator("player-fitness player-points")
            form_vals = [_to_int_generic(c.inner_text()) for c in form_cells.all()]
        except Exception:
            form_vals = []

        form = (form_vals[:5] + [0] * 5)[:5]

        data.append(
            {
                "name": name,
                "points": points,
                "market_value": market_value,
                "mv_change_eur": mv_change_eur,
                "status": status,
                "games_played": gp,
                "average_points": avg,
                "form_t-1": form[0],
                "form_t-2": form[1],
                "form_t-3": form[2],
                "form_t-4": form[3],
                "form_t-5": form[4],
            }
        )

    return pd.DataFrame(data)

