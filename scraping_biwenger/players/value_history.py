# scraping_biwenger/players/value_history.py

from __future__ import annotations
from typing import Optional, Dict
from io import StringIO
import re
import time
import pandas as pd
from playwright.sync_api import Page, Download, TimeoutError as PWTimeout

from scraping_biwenger.shared.timing import log_timing_debug

CSV_BTN = "segmented-control button:has(.icon-download)"
IMG_BTN = "segmented-control button:has(.icon-image)"
VALUE_TAB = "tab[header='Value'], [role='tab']:has-text('Value')"
CHART_CANVAS = "chart-js canvas"
TOOLS = "chart-js .tools segmented-control"

def _log_timing(logger, label: str, started_at: float, *, player_slug: str = "") -> None:
    log_timing_debug(logger, label, started_at, player_slug=player_slug)

def _hover_chart_to_reveal_tools(page: Page, timeout: float = 3000) -> None:
    # Hover the canvas to reveal the segmented-control with the CSV/PNG buttons.
    page.locator(CHART_CANVAS).wait_for(state="visible", timeout=timeout)
    page.locator(CHART_CANVAS).hover()
    # The tools often fade in; give them a moment.
    page.locator(TOOLS).wait_for(state="visible", timeout=timeout)

def open_value_tab(page: Page, timeout: float = 5000) -> bool:
    """
    Click the 'Value' tab and wait for the chart to render.
    Safe to call even if already active.
    """
    try:
        # Prefer the ARIA role first (most robust across Angular versions).
        tab = page.get_by_role("tab", name=re.compile(r"^\s*Value\s*$", re.I))
        if tab.count() > 0:
            tab.first.click()
        else:
            page.locator(VALUE_TAB).first.click()
        page.locator(CHART_CANVAS).wait_for(state="visible", timeout=timeout)
        return True
    except PWTimeout:
        return False

def click_download_csv(page: Page, timeout: float = 5000) -> Optional[Download]:
    """
    Hover chart → click CSV button → return Playwright Download handle.
    Requires the browser context to be created with accept_downloads=True.
    """
    _hover_chart_to_reveal_tools(page, timeout=timeout)

    with page.expect_download(timeout=timeout) as dl_info:
        page.locator(CSV_BTN).click()
    return dl_info.value

def parse_value_csv_text(csv_text: str) -> pd.DataFrame:
    """
    Convert Biwenger value CSV text to a normalized DataFrame with:
      ['date', 'market_value_eur']
    Handles Biwenger's 'Date;' header, missing value headers, and timezone strings.
    """
    df = None
    for sep in (";", ",", "\t"):
        try:
            df = pd.read_csv(StringIO(csv_text or ""), sep=sep, engine="python")
            if df.shape[1] >= 2:
                break
        except Exception:
            continue
    if df is None or df.shape[1] < 2:
        return pd.DataFrame(columns=["date", "market_value_eur"])

    # 2) Normalize column names (e.g., 'Date' and 'Unnamed: 1')
    df.columns = [str(c).lower().strip() for c in df.columns]
    date_col = next((c for c in df.columns if "date" in c), df.columns[0])
    # value header is usually missing → ends up as 'unnamed: 1'
    val_col = next((c for c in df.columns if any(k in c for k in ("value","precio","price","valor"))),
                   df.columns[-1])

    # 3) Clean dates: drop parenthetical TZ name and 'GMT', then parse with utc=True
    import re
    def _clean_date(s):
        if pd.isna(s): return None
        s = str(s)
        s = re.sub(r"\s*\([^)]*\)", "", s)   # remove " (Central European Summer Time)"
        s = s.replace("GMT", "").strip()     # "GMT+0200" → "+0200"
        return s

    dt = pd.to_datetime(df[date_col].map(_clean_date), errors="coerce", utc=True)

    # 4) Numeric value
    vals = pd.to_numeric(df[val_col], errors="coerce")

    out = pd.DataFrame({
        "date": dt.dt.strftime("%Y-%m-%d"),  # string, JSON-safe
        "market_value_eur": pd.to_numeric(vals, errors="coerce")
    })

    out = out.dropna(subset=["date", "market_value_eur"]).reset_index(drop=True)
    return out[["date", "market_value_eur"]]


def _read_price_csv_to_df(download: Download) -> pd.DataFrame:
    """
    Convert the downloaded CSV file to a normalized DataFrame with:
      ['date', 'market_value_eur']
    """
    path = download.path()
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            return parse_value_csv_text(fh.read())
    except Exception:
        return pd.DataFrame(columns=["date", "market_value_eur"])


def scrape_value_history_for_player(
    page: Page,
    logger=None,
    player_ctx: Optional[Dict[str, str]] = None,
    timeout: float = 7000,
) -> pd.DataFrame:
    """
    Open Value tab → click CSV download → parse to DataFrame.
    Enriches rows with player context if provided.
    """
    player_slug = (player_ctx or {}).get("slug", "")
    started_at = time.time()
    step_started_at = time.time()
    ok = open_value_tab(page, timeout=timeout)
    _log_timing(logger, "Value tab open/wait", step_started_at, player_slug=player_slug)
    if not ok:
        if logger: logger.warning("Could not open Value tab.")
        return pd.DataFrame(columns=["date", "market_value_eur"])

    try:
        step_started_at = time.time()
        dl = click_download_csv(page, timeout=timeout)
        _log_timing(logger, "Value CSV download", step_started_at, player_slug=player_slug)
    except PWTimeout:
        _log_timing(logger, "Value CSV download failed", step_started_at, player_slug=player_slug)
        if logger: logger.warning("CSV download did not start in time.")
        return pd.DataFrame(columns=["date", "market_value_eur"])

    step_started_at = time.time()
    df = _read_price_csv_to_df(dl)
    _log_timing(logger, "Value CSV parse", step_started_at, player_slug=player_slug)

    # Add optional context (player_name, team, slug, etc.)
    if player_ctx:
        for k, v in player_ctx.items():
            df[k] = v

    if logger:
        logger.debug("Value history rows for %s: %s", player_slug or "(unknown)", len(df))
        _log_timing(logger, "Value history full scrape", started_at, player_slug=player_slug)

    return df
