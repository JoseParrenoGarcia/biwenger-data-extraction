# scraping_biwenger/helper_player_value.py

from __future__ import annotations
from typing import Optional, List, Dict
import re
import time
import pandas as pd
from playwright.sync_api import Page, Download, TimeoutError as PWTimeout

CSV_BTN = "segmented-control button:has(.icon-download)"
IMG_BTN = "segmented-control button:has(.icon-image)"
VALUE_TAB = "tab[header='Value'], [role='tab']:has-text('Value')"
CHART_CANVAS = "chart-js canvas"
TOOLS = "chart-js .tools segmented-control"

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

def _read_price_csv_to_df(download: Download) -> pd.DataFrame:
    """
    Convert the downloaded CSV file to a normalized DataFrame with:
      ['date', 'market_value_eur']
    Tries common delimiters and currency formats.
    """
    path = download.path()
    # Pandas sniffing: try ',', then ';', then '\t'
    for sep in (",", ";", "\t"):
        try:
            df = pd.read_csv(path, sep=sep)
            if df.shape[1] >= 2:
                break
        except Exception:
            continue

    # Heuristic: find the most likely date & value columns.
    cols = [c.lower().strip() for c in df.columns]
    df.columns = cols

    date_col = next((c for c in cols if "date" in c or "fecha" in c), cols[0])
    val_col = next(
        (c for c in cols if any(k in c for k in ("value", "precio", "price", "valor"))),
        cols[1] if len(cols) > 1 else cols[0],
    )

    out = df[[date_col, val_col]].copy()

    # Parse dates
    out["date"] = pd.to_datetime(out[date_col], errors="coerce").dt.date

    # Normalize euros like "€1,990,000" or "1.990.000 €"
    def _to_number(x):
        if pd.isna(x):
            return None
        s = str(x)
        s = s.replace("€", "").replace(" ", "")
        # Handle Spanish thousands '.' and decimal ',' if ever present
        s = s.replace(".", "").replace(",", "")
        try:
            return float(s)
        except Exception:
            return None

    out["market_value_eur"] = out[val_col].map(_to_number)
    out = out.dropna(subset=["date", "market_value_eur"]).reset_index(drop=True)
    return out[["date", "market_value_eur"]]

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
    ok = open_value_tab(page, timeout=timeout)
    page.pause()
    # if not ok:
    #     if logger: logger.warning("Could not open Value tab.")
    #     return pd.DataFrame(columns=["date", "market_value_eur"])

    # try:
    #     dl = click_download_csv(page, timeout=timeout)
    # except PWTimeout:
    #     if logger: logger.warning("CSV download did not start in time.")
    #     return pd.DataFrame(columns=["date", "market_value_eur"])
    #
    # df = _read_price_csv_to_df(dl)
    #
    # # Add optional context (player_name, team, slug, etc.)
    # if player_ctx:
    #     for k, v in player_ctx.items():
    #         df[k] = v
    #
    # if logger:
    #     logger.info(f"💾 Value history rows: {len(df)} (e.g., {df.head(1).to_dict(orient='records')})")

    df = pd.DataFrame(columns=["date", "market_value_eur"])

    return df
