from typing import Callable, List, Dict, Optional, Tuple
from playwright.sync_api import Page
import random, time

from scraping_biwenger.shared.timing import log_timing_debug
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

def _log_timing(logger, label: str, started_at: float, *, player_slug: str = "") -> None:
    log_timing_debug(logger, label, started_at, player_slug=player_slug)

def scrape_all_players_detail(
    logger,
    page: Page,
    players_list: List[Dict[str, str]],
    max_players: Optional[int] = None,
    base_url: str = "https://biwenger.as.com",
    collect_matches: bool = True,
    on_player_payload: Optional[Callable[..., None]] = None,
    on_player_error: Optional[Callable[..., None]] = None,
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

    def record_player_error(player: Dict[str, str], stage: str, message: str) -> None:
        if on_player_error:
            on_player_error(player=player, stage=stage, message=message)

    def log_player_summary(
        player: Dict[str, str],
        *,
        idx: int,
        total: int,
        status: str,
        started_at: float,
        stats_rows: int = 0,
        match_count: int = 0,
        value_count: int = 0,
        stage: str = "",
    ) -> None:
        if not logger:
            return
        logger.info(
            "Player %s/%s | %s | %s | scoring=%s stats=%s matches=%s values=%s checkpoint=%s stage=%s | %.2fs",
            idx,
            total,
            player.get("slug") or player.get("name", ""),
            player.get("attempt", "initial"),
            player.get("_scoring_system", "n/a"),
            status if stats_rows else "none",
            match_count,
            value_count,
            player.get("_checkpoint_status", "n/a"),
            stage or "ok",
            time.time() - started_at,
        )

    for idx, player in enumerate(players_list, start=1):
        player_started_at = time.time()
        if max_players and processed >= max_players:
            logger.info(f"⛔ Reached max_players={max_players}. Stopping early.")
            break

        name = player.get("name", "")
        slug = player.get("slug", "")
        logger.debug("Opening player %s/%s: %s (%s)", idx, len(players_list), name, slug)

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
            record_player_error(player, "open_player", "Could not open player detail.")
            if needs_table_return():
                back_started_at = time.time()
                click_back_to_players_table(page)
                _log_timing(logger, "Back-to-table after failed open", back_started_at, player_slug=slug)
            else:
                logger.debug("Skipping back-to-table for final selected player: %s", name)
            log_player_summary(
                player,
                idx=idx,
                total=len(players_list),
                status="failed",
                started_at=player_started_at,
                stage="open_player",
            )
            continue

        try:
            scoring_started_at = time.time()
            scoring_system = select_scoring_system(page, target_label="SofaScore", logger=logger)
            player["_scoring_system"] = scoring_system
            _log_timing(logger, "SofaScore selection", scoring_started_at, player_slug=slug)
        except Exception as e:
            logger.exception(f"Skipping {name} — could not select SofaScore scoring system: {e}")
            record_player_error(player, "select_scoring_system", str(e))
            if needs_table_return():
                back_started_at = time.time()
                click_back_to_players_table(page)
                _log_timing(logger, "Back-to-table after scoring-system failure", back_started_at, player_slug=slug)
            else:
                logger.debug("Skipping back-to-table for final selected player: %s", name)
            log_player_summary(
                player,
                idx=idx,
                total=len(players_list),
                status="failed",
                started_at=player_started_at,
                stage="select_scoring_system",
            )
            continue

        # 2) scrape left-panel stats
        detail = None
        player_match_rows: List[Dict[str, str]] = []
        player_value_history_rows: List[Dict[str, str]] = []
        try:
            detail_started_at = time.time()
            detail = scrape_player_detail(page, logger=logger)
            _log_timing(logger, "Detail scrape", detail_started_at, player_slug=slug)
            detail.update({
                "name": name,
                "slug": slug,
                "href": player.get("href", ""),
                "scoring_system": scoring_system,
            })
            player_detail_rows.append(detail)
            processed += 1
            logger.debug(
                "Stats scraped for %s: %s",
                name,
                {k: detail.get(k) for k in ['points','value','matches_played','average','market_purchases_pct','market_sales_pct']},
            )
        except Exception as e:
            logger.exception(f"Failed scraping stats for '{name}': {e}")
            record_player_error(player, "scrape_detail", str(e))
            if needs_table_return():
                back_started_at = time.time()
                click_back_to_players_table(page)
                _log_timing(logger, "Back-to-table after detail failure", back_started_at, player_slug=slug)
            else:
                logger.debug("Skipping back-to-table for final selected player: %s", name)
            log_player_summary(
                player,
                idx=idx,
                total=len(players_list),
                status="failed",
                started_at=player_started_at,
                stage="scrape_detail",
            )
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
                player_match_rows.extend(rows)

                logger.debug("Matches scraped for %s: %s rows", name, len(rows))
                _log_timing(logger, "Matches scrape", matches_started_at, player_slug=slug)
            except Exception as e:
                logger.warning(f"⚠️ Failed to scrape matches for {name}: {e}")
                record_player_error(player, "scrape_matches", str(e))

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
                player_value_history_rows = vdf.to_dict(orient="records")
                value_history_rows.extend(player_value_history_rows)
                logger.debug("Value history captured for %s: %s rows", name, len(vdf))
            else:
                logger.debug("Value history empty for %s", name)
            _log_timing(logger, "Value history scrape", value_started_at, player_slug=slug)
        except Exception as e:
            logger.warning(f"⚠️ Failed to scrape value history for {name}: {e}")
            record_player_error(player, "scrape_value_history", str(e))

        if on_player_payload:
            on_player_payload(
                player=player,
                detail_rows=[detail],
                match_rows=player_match_rows,
                value_history_rows=player_value_history_rows,
                processed_count=processed,
            )

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
            _log_timing(logger, "Back-to-table", back_started_at, player_slug=slug)
        else:
            logger.debug("Skipping back-to-table for final selected player: %s", name)

        _cooldown()
        _log_timing(logger, "Full player cycle", player_started_at, player_slug=slug)
        log_player_summary(
            player,
            idx=idx,
            total=len(players_list),
            status="ok",
            started_at=player_started_at,
            stats_rows=1,
            match_count=len(player_match_rows),
            value_count=len(player_value_history_rows),
        )
        if processed % 20 == 0 and processed > 0:
            _cooldown(500, 1500)

    logger.info(f"🏁 Done. Players processed: {processed}. "
                f"Detail rows: {len(player_detail_rows)}, Match rows: {len(match_rows)}")

    return player_detail_rows, match_rows, value_history_rows
