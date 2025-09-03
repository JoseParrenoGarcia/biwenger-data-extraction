from typing import List, Dict, Optional, Tuple
from playwright.sync_api import Page
import random, time

from helper_search_and_open_player import (
    open_player_via_search,
    click_back_to_players_table,
    clear_search_box_if_present,
)
from helper_players_detail import scrape_player_detail
from helper_player_value import open_value_tab, click_download_csv, scrape_value_history_for_player

# 👇 import your existing match helpers wherever you put them
from helper_player_matches import (
    open_points_tab,
    scrape_player_matches,
    with_retries,
)

def _cooldown(min_ms=300, max_ms=900):
    time.sleep(random.uniform(min_ms / 1000, max_ms / 1000))

def scrape_all_players_detail(
    logger,
    page: Page,
    players_list: List[Dict[str, str]],
    max_players: Optional[int] = None,
    base_url: str = "https://biwenger.as.com",
    collect_matches: bool = True,
) -> Tuple[List[Dict[str, str]], List[Dict[str, str]], List[Dict[str, str]]]:
    """
    Iterate players_list → open → scrape detail (left panel) → scrape matches (Points tab) → back.
    Returns:
        (player_detail_rows, match_rows)
    """
    player_detail_rows: List[Dict[str, str]] = []
    match_rows: List[Dict[str, str]] = []
    value_history_rows: List[Dict[str, str]] = []
    processed = 0

    for idx, player in enumerate(players_list, start=1):
        if max_players and processed >= max_players:
            logger.info(f"⛔ Reached max_players={max_players}. Stopping early.")
            break

        name = player.get("name", "")
        slug = player.get("slug", "")
        logger.info(f"🔎 [{idx}/{len(players_list)}] Opening player: {name} ({slug})")

        # 1) open the player page
        opened = open_player_via_search(logger, page, player, base_url=base_url)
        if not opened:
            logger.warning(f"Skipping {name} — could not open detail.")
            click_back_to_players_table(page)
            continue

        # 2) scrape left-panel stats
        try:
            detail = scrape_player_detail(page)
            detail.update({
                "name": name,
                "slug": slug,
                "href": player.get("href", ""),
            })
            player_detail_rows.append(detail)
            processed += 1
            logger.info(f"✅ Stats scraped for {name}: "
                        f"{ {k: detail.get(k) for k in ['points','value','matches_played','average','market_purchases_pct','market_sales_pct']} }")
        except Exception as e:
            logger.exception(f"Failed scraping stats for '{name}': {e}")

        # 3) scrape matches (Points tab) while page is still open
        if collect_matches:
            try:
                # your own helpers with a light retry
                _ = open_points_tab(page)  # safe if already active
                rows = with_retries(
                    lambda: scrape_player_matches(page, logger=logger),
                    validate=lambda r: r is not None and len(r) > 0,
                    attempts=2, base_sleep=0.6, logger=logger
                ) or []

                # enrich each row with player context
                for r in rows:
                    r["player_name"] = detail.get("player_name", "") or name
                    r["team"] = detail.get("team", "")
                match_rows.extend(rows)

                logger.info(f"📊 Matches scraped for {name}: {len(rows)} rows")
            except Exception as e:
                logger.warning(f"⚠️ Failed to scrape matches for {name}: {e}")

        # 4) Scrape value history (Value tab)
        try:
            vdf = scrape_value_history_for_player(
                page,
                logger=logger,
                player_ctx={"player_name": name, "team": detail.get("team", ""), "slug": slug},
                timeout=7000,
            )
            if not vdf.empty:
                value_history_rows.extend(vdf.to_dict(orient="records"))
                logger.info(f"📈 Value history captured for {name}: {len(vdf)} rows")
            else:
                logger.info(f"📈 Value history empty for {name}")
        except Exception as e:
            logger.warning(f"⚠️ Failed to scrape value history for {name}: {e}")

        # 5) back to table for next player
        if not click_back_to_players_table(page):
            logger.warning("Back-to-table failed; forcing go_back() and clearing search.")
            try:
                page.go_back(wait_until="domcontentloaded")
                clear_search_box_if_present(page)
            except Exception:
                pass

        _cooldown()
        if processed % 20 == 0 and processed > 0:
            _cooldown(1500, 2500)

    logger.info(f"🏁 Done. Players processed: {processed}. "
                f"Detail rows: {len(player_detail_rows)}, Match rows: {len(match_rows)}")

    return player_detail_rows, match_rows, value_history_rows
