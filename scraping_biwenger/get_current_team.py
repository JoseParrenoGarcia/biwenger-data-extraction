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
import time
from playwright.sync_api import TimeoutError as PWTimeout
import re

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
    # normalize minus and strip currency/whitespace
    t = (text.replace("€", "")
              .replace("\u2212", "-")   # unicode minus
              .replace(",", "")
              .replace(".", "")
              .strip())

    NUM_RE = re.compile(r"[-\d]+")
    m = NUM_RE.findall(t)
    if not m:
        return 0
    return int("".join(m)) if t.startswith("-") else int("".join(m))

def _mv_change_from_increment(row) -> int:
    """
    <td class="tr ng-star-inserted">
      <increment class="icon ... increment|decrement|equal" aria-label="€90,000">€90,000</increment>
    </td>
    Return signed int in euros.
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
    # class could be 'equal'
    return 0 if val == 0 else val

def _status_from_element(row) -> str:
    """
    Status is in <player-status ... aria-label="Fit" title="Fit" class="... success|danger|warning ...">
    Prefer aria-label, then fall back to class hints.
    """
    el = row.locator("player-status").first
    if el.count() == 0:
        return "unknown"
    try:
        aria = el.get_attribute("aria-label") or el.get_attribute("title") or ""
        aria = aria.strip()
        if aria:
            # normalize short
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
        cls = el.get_attribute("class") or ""
        cls = cls.lower()
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
    Scrapes: name, points, market_value, mv_change_eur (signed),
             status, GP, Avg, Form (max 5; leftmost = latest).
    """
    # Wait for the table to be ready
    try:
        page.wait_for_selector("table.table.no-swipe tbody tr", timeout=8000, state="attached")
    except PWTimeout:
        return pd.DataFrame([])

    rows = page.locator("table.table.no-swipe tbody tr")
    n = rows.count()

    data = []
    for i in range(n):
        row = rows.nth(i)

        # name
        try:
            name = row.locator("th.text-left a").first.inner_text().strip()
        except Exception:
            name = ""

        # points (the <td> immediately after the name <th>)
        try:
            points_td = row.locator("th.text-left").locator("xpath=following-sibling::td[1]")
            points = _to_int_generic(points_td.inner_text())
        except Exception:
            points = 0

        # market value
        try:
            mv_text = row.locator("td.tr").first.inner_text().strip()
            market_value = _to_int_money(mv_text)
        except Exception:
            market_value = 0

        # mv change (signed, in euros)
        mv_change_eur = _mv_change_from_increment(row)

        # status
        status = _status_from_element(row)

        # GP and Avg: take the first and second <td> after the status cell
        try:
            status_td = row.locator("player-status").first.locator("xpath=..")  # parent TD
            gp_td = status_td.locator("xpath=following-sibling::td[1]")
            avg_td = status_td.locator("xpath=following-sibling::td[2]")
            gp = _to_int_generic(gp_td.inner_text())
            avg = _to_float_generic(avg_td.inner_text())
        except Exception:
            gp, avg = 0, 0.0

        # Form (up to last 5 numbers; leftmost = latest)
        try:
            form_cells = row.locator("player-fitness player-points")
            form_vals = [_to_int_generic(c.inner_text()) for c in form_cells.all()]
        except Exception:
            form_vals = []

        # Guarantee at most 5, pad right with 0s if fewer
        form = (form_vals[:5] + [0] * 5)[:5]

        data.append({
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
        })

    df = pd.DataFrame(data)
    if not df.empty:
        df['name'] = df['name'].astype(str)
        df["points"] = df["points"].astype(int)
        df["market_value"] = df["market_value"].astype(int)
        df["mv_change_eur"] = df["mv_change_eur"].astype(int)
        df['status'] = df['status'].astype(str)
        df["games_played"] = df["games_played"].astype(int)
        df["average_points"] = df["average_points"].astype(float)
        for j in range(1, 6):
            df[f"form_t-{j}"] = df[f"form_t-{j}"].astype(int)

    return df

def insert_current_team(df: pd.DataFrame, table_name: str, logger) -> None:
    """
    Inserts rows into Supabase table `table_name`.
    Assumes table exists and has its own PK/timestamp.
    """
    supabase = get_supabase_client()

    if not check_if_table_exists(supabase, table_name):
        logger.error(f"❌ Table '{table_name}' does not exist. Create it first.")
        return

    if df is None or df.empty:
        logger.warning("⚠️ No rows to insert (empty dataframe).")
        return

    rows = df.to_dict(orient="records")
    try:
        insert_rows_into_table(supabase, table_name=table_name, rows=rows)
        logger.info(f"✅ Inserted {len(rows)} rows into '{table_name}'.")
    except Exception as e:
        logger.exception(f"❌ Failed to insert into '{table_name}': {e}")

def ETL_get_current_team():
    """
    ETL: Login to Biwenger, scrape current team stats, and (later) upload to Supabase.
    For now, this sets up logging and loads credentials.
    """
    logger = get_logger(
        "ETL_get_current_team",
        log_file="logs/ETL_get_current_team.log"
    )
    logger.info("=" * 70)
    logger.info("🚀 Starting ETL: get_current_team")
    logger.info("=" * 70)

    # 1) Load credentials (from secrets/biwenger.toml)
    creds = load_biwenger_credentials()
    logger.info("✅ Credentials loaded successfully.")

    # 2) Start browser
    pw, browser, context, page = start_browser_accept_cookies(headless=True)
    logger.info("✅ Logged in")

    # 3) Login
    perform_login(page, creds["email"], creds["password"])

    # 4) Navigate to team page
    click_tab_in_horizontal_main_menu(page, "team")

    # 5) Click view as list
    page.get_by_role("button", name="Table").click()

    # 6) Scroll to list section
    scroll_into_view(page, "segmented-control button[aria-label='Squad']")

    # 7) Extract table data
    team_data = scrape_basic_team_table(page)

    # 8) Insert into Supabase
    insert_current_team(team_data, table_name="biwenger_current_team", logger=logger)


if __name__ == "__main__":
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)
    pd.set_option('display.max_colwidth', None)

    ETL_get_current_team()