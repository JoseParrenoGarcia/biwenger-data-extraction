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


def _find_numbers(text: str) -> list[str]:
    if text is None:
        return []
    return re.findall(r"-?\d+(?:\.\d+)?", text.replace("\u2212", "-"))


def _to_int_money(text: str) -> int:
    """Convert '€2,370,000' -> 2370000; handles unicode minus and spaces."""
    if text is None:
        return 0

    t = text.replace("€", "").replace("\u2212", "-").replace(",", "").replace(".", "").strip()

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


def _direct_cell(row, index: int):
    return row.locator("xpath=./*[self::td or self::th]").nth(index)


def _safe_inner_text(locator) -> str:
    try:
        return locator.inner_text().strip()
    except Exception:
        return ""


def _safe_attr(locator, attr: str) -> str | None:
    try:
        value = locator.get_attribute(attr)
        return value.strip() if value else None
    except Exception:
        return None


def _slug_from_url(url: str | None) -> str | None:
    if not url:
        return None
    return url.rstrip("/").split("/")[-1] or None


def _match_id_from_url(url: str | None) -> int | None:
    slug = _slug_from_url(url)
    if not slug or not slug.isdigit():
        return None
    return int(slug)


def _points_average_from_split_cell(cell) -> tuple[int, float]:
    numbers = _find_numbers(_safe_inner_text(cell))
    if not numbers:
        return 0, 0.0
    points = int(float(numbers[0]))
    average = float(numbers[1]) if len(numbers) > 1 else 0.0
    return points, average


def _previous_season_points(points_cell) -> int | None:
    previous = points_cell.locator("div.text-muted.small[title*='season points']").first
    if previous.count() == 0:
        return None
    return _to_int_generic(_safe_inner_text(previous))


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
        position_cell = _direct_cell(row, 0)
        team_cell = _direct_cell(row, 1)
        player_cell = _direct_cell(row, 2)
        points_cell = _direct_cell(row, 3)
        market_value_cell = _direct_cell(row, 4)
        home_cell = _direct_cell(row, 9)
        away_cell = _direct_cell(row, 10)
        play_cell = _direct_cell(row, 11)
        opponent_cell = _direct_cell(row, 12)

        position_el = position_cell.locator("player-position").first
        position_short = _safe_inner_text(position_el) or None
        position = _safe_attr(position_el, "aria-label") or _safe_attr(position_el, "title")

        team_link = team_cell.locator("a.team").first
        team_name = _safe_attr(team_link, "title") if team_link.count() else None

        player_link = player_cell.locator("a").first
        player_url = _safe_attr(player_link, "href") if player_link.count() else None
        player_slug = _slug_from_url(player_url)

        try:
            name = player_link.inner_text().strip()
        except Exception:
            name = ""

        try:
            points = _to_int_generic(points_cell.inner_text())
        except Exception:
            points = 0
        previous_points = _previous_season_points(points_cell)

        try:
            market_value = _to_int_money(market_value_cell.inner_text().strip())
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

        home_points, home_average_points = _points_average_from_split_cell(home_cell)
        away_points, away_average_points = _points_average_from_split_cell(away_cell)
        next_fixture_location = _safe_inner_text(play_cell) or None

        opponent_link = opponent_cell.locator("a").first
        next_opponent = _safe_attr(opponent_link, "title") if opponent_link.count() else None
        next_match_url = _safe_attr(opponent_link, "href") if opponent_link.count() else None
        next_match_id = _match_id_from_url(next_match_url)

        try:
            form_cells = row.locator("player-fitness player-points")
            form_vals = [_to_int_generic(c.inner_text()) for c in form_cells.all()]
        except Exception:
            form_vals = []

        form = (form_vals[:5] + [0] * 5)[:5]

        data.append(
            {
                "name": name,
                "position_short": position_short,
                "position": position,
                "team_name": team_name,
                "player_slug": player_slug,
                "player_url": player_url,
                "points": points,
                "previous_season_points": previous_points,
                "market_value": market_value,
                "mv_change_eur": mv_change_eur,
                "status": status,
                "games_played": gp,
                "average_points": avg,
                "home_points": home_points,
                "home_average_points": home_average_points,
                "away_points": away_points,
                "away_average_points": away_average_points,
                "next_fixture_location": next_fixture_location,
                "next_opponent": next_opponent,
                "next_match_url": next_match_url,
                "next_match_id": next_match_id,
                "form_t-1": form[0],
                "form_t-2": form[1],
                "form_t-3": form[2],
                "form_t-4": form[3],
                "form_t-5": form[4],
            }
        )

    return pd.DataFrame(data)
