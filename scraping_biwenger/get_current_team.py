from config_logging import get_logger
from scraping_biwenger.scraper_actions_in_biwenger import (
    load_biwenger_credentials,
    start_browser_accept_cookies,
    perform_login,
    click_tab_in_horizontal_main_menu,
    scroll_into_view
)

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

        data.append({
            "name": name,
            "points": points,
            "market_value": market_value,
        })

    df = pd.DataFrame(data)
    return df

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
    print(team_data)
    print(team_data.dtypes)

    page.pause()




if __name__ == "__main__":
    ETL_get_current_team()