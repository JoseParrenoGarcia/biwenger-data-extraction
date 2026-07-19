from typing import List, Dict, Optional, Tuple
from playwright.sync_api import Page
import random, time

from scraping_biwenger.players.search_and_open import (
    open_player_via_search,
    click_back_to_players_table,
    clear_search_box_if_present,
)
from scraping_biwenger.players.detail import scrape_player_detail
from scraping_biwenger.players.value_history import open_value_tab, click_download_csv, scrape_value_history_for_player

from scraping_biwenger.players.matches import (
    open_points_tab,
    scrape_player_matches,
    select_scoring_system,
    with_retries,
)

def _cooldown(min_ms=300, max_ms=900):
    time.sleep(random.uniform(min_ms / 1000, max_ms / 1000))

def _log_timing(logger, label: str, started_at: float) -> None:
    if logger:
        logger.info("%s completed in %.2fs", label, time.time() - started_at)

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
        player_started_at = time.time()
        if max_players and processed >= max_players:
            logger.info(f"⛔ Reached max_players={max_players}. Stopping early.")
            break

        name = player.get("name", "")
        slug = player.get("slug", "")
        logger.info(f"🔎 [{idx}/{len(players_list)}] Opening player: {name} ({slug})")

        def needs_table_return() -> bool:
            if idx >= len(players_list):
                return False
            if max_players and processed >= max_players:
                return False
            return True

        # 1) open the player page
        opened = open_player_via_search(logger, page, player, base_url=base_url)
        if not opened:
            logger.warning(f"Skipping {name} — could not open detail.")
            if needs_table_return():
                back_started_at = time.time()
                click_back_to_players_table(page)
                _log_timing(logger, f"Back-to-table after failed open for {name}", back_started_at)
            else:
                logger.info(f"Skipping back-to-table for final selected player: {name}")
            continue

        try:
            scoring_started_at = time.time()
            scoring_system = select_scoring_system(page, target_label="SofaScore", logger=logger)
            _log_timing(logger, f"SofaScore selection for {name}", scoring_started_at)
        except Exception as e:
            logger.exception(f"Skipping {name} — could not select SofaScore scoring system: {e}")
            if needs_table_return():
                back_started_at = time.time()
                click_back_to_players_table(page)
                _log_timing(logger, f"Back-to-table after scoring-system failure for {name}", back_started_at)
            else:
                logger.info(f"Skipping back-to-table for final selected player: {name}")
            continue

        # 2) scrape left-panel stats
        detail = None
        try:
            detail_started_at = time.time()
            detail = scrape_player_detail(page, logger=logger)
            _log_timing(logger, f"Detail scrape for {name}", detail_started_at)
            detail.update({
                "name": name,
                "slug": slug,
                "href": player.get("href", ""),
                "scoring_system": scoring_system,
            })
            player_detail_rows.append(detail)
            processed += 1
            logger.info(f"✅ Stats scraped for {name}: "
                        f"{ {k: detail.get(k) for k in ['points','value','matches_played','average','market_purchases_pct','market_sales_pct']} }")
        except Exception as e:
            logger.exception(f"Failed scraping stats for '{name}': {e}")
            if needs_table_return():
                back_started_at = time.time()
                click_back_to_players_table(page)
                _log_timing(logger, f"Back-to-table after detail failure for {name}", back_started_at)
            else:
                logger.info(f"Skipping back-to-table for final selected player: {name}")
            continue

        # 3) scrape matches (Points tab) while page is still open
        if collect_matches:
            try:
                matches_started_at = time.time()
                # your own helpers with a light retry
                _ = open_points_tab(page, logger=logger)  # safe if already active
                rows = with_retries(
                    lambda: scrape_player_matches(page, logger=logger),
                    validate=lambda r: r is not None and len(r) > 0,
                    attempts=2, base_sleep=0.6, logger=logger
                ) or []

                # enrich each row with player context
                for r in rows:
                    r["player_name"] = detail.get("player_name", "") or name
                    r["team"] = detail.get("team", "")
                    r["slug"] = slug
                    r["scoring_system"] = scoring_system
                match_rows.extend(rows)

                logger.info(f"📊 Matches scraped for {name}: {len(rows)} rows")
                _log_timing(logger, f"Matches scrape for {name}", matches_started_at)
            except Exception as e:
                logger.warning(f"⚠️ Failed to scrape matches for {name}: {e}")

        # 4) Scrape value history (Value tab)
        try:
            value_started_at = time.time()
            vdf = scrape_value_history_for_player(
                page,
                logger=logger,
                player_ctx={
                    "player_name": detail.get("player_name", "") or name,
                    "team": detail.get("team", ""),
                    "slug": slug,
                },
                timeout=7000,
            )
            if not vdf.empty:
                value_history_rows.extend(vdf.to_dict(orient="records"))
                logger.info(f"📈 Value history captured for {name}: {len(vdf)} rows")
            else:
                logger.info(f"📈 Value history empty for {name}")
            _log_timing(logger, f"Value history scrape for {name}", value_started_at)
        except Exception as e:
            logger.warning(f"⚠️ Failed to scrape value history for {name}: {e}")

        # 5) back to table for next player
        if needs_table_return():
            back_started_at = time.time()
            if not click_back_to_players_table(page):
                logger.warning("Back-to-table failed; forcing go_back() and clearing search.")
                try:
                    page.go_back(wait_until="domcontentloaded")
                    clear_search_box_if_present(page)
                except Exception:
                    pass
            _log_timing(logger, f"Back-to-table for {name}", back_started_at)
        else:
            logger.info(f"Skipping back-to-table for final selected player: {name}")

        _cooldown()
        _log_timing(logger, f"Full player cycle for {name}", player_started_at)
        if processed % 20 == 0 and processed > 0:
            _cooldown(500, 1500)

    logger.info(f"🏁 Done. Players processed: {processed}. "
                f"Detail rows: {len(player_detail_rows)}, Match rows: {len(match_rows)}")

    return player_detail_rows, match_rows, value_history_rows
