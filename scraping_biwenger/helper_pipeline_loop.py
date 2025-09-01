from typing import List, Dict, Optional
from playwright.sync_api import Page
import random, time

from helper_search_and_open_player import (
    open_player_via_search,
    click_back_to_players_table,
    clear_search_box_if_present,
)
from helper_players_detail import scrape_player_detail

def _cooldown(min_ms=300, max_ms=900):
    time.sleep(random.uniform(min_ms / 1000, max_ms / 1000))

def scrape_all_players_detail(
    logger,
    page: Page,
    players_list: List[Dict[str, str]],
    max_players: Optional[int] = None,
    base_url: str = "https://biwenger.as.com",
) -> List[Dict[str, str]]:
    """
    Iterate players_list → open → scrape detail → back.
    Returns a list of enriched dicts.
    """
    results: List[Dict[str, str]] = []
    processed = 0

    for idx, player in enumerate(players_list, start=1):
        if max_players and processed >= max_players:
            logger.info(f"⛔ Reached max_players={max_players}. Stopping early.")
            break

        name = player.get("name", "")
        slug = player.get("slug", "")
        logger.info(f"🔎 [{idx}/{len(players_list)}] Opening player: {name} ({slug})")

        # Step 1: open detail
        opened = open_player_via_search(logger, page, player, base_url=base_url)
        if not opened:
            logger.warning(f"Skipping {name} — could not open detail.")
            click_back_to_players_table(page)  # ensure we’re back in table
            continue

        # Step 2: scrape detail
        try:
            detail = scrape_player_detail(page)
            detail.update({
                "name": name,
                "slug": slug,
                "href": player.get("href", ""),
            })
            results.append(detail)
            processed += 1
            logger.info(f"✅ Scraped {name}: { {k: detail.get(k) for k in ['points','value','matches_played','average']} }")
        except Exception as e:
            logger.exception(f"Failed scraping {name}: {e}")

        # Step 3: back to table
        if not click_back_to_players_table(page):
            logger.warning("Back-to-table failed; forcing reload.")
            try:
                page.go_back(wait_until="domcontentloaded")
                clear_search_box_if_present(page)
            except Exception:
                pass

        _cooldown()  # small pause each loop
        if processed % 20 == 0:  # bigger pause every 20 players
            _cooldown(1500, 2500)

    logger.info(f"🏁 Done. Processed {processed} players. Returning {len(results)} results.")
    return results
