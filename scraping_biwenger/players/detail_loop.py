import random
import time
from typing import Callable, Dict, List, Optional, Tuple

from playwright.sync_api import Page

from scraping_biwenger.players.detail import scrape_player_detail
from scraping_biwenger.players.matches import (
    scrape_player_matches,
    select_scoring_system,
    with_retries,
)
from scraping_biwenger.players.network_telemetry import network_action
from scraping_biwenger.players.pacing import PlayerRunPacingPolicy
from scraping_biwenger.players.search_and_open import (
    clear_search_box_if_present,
    click_back_to_players_table,
    open_player_detail,
)
from scraping_biwenger.players.value_history import scrape_value_history_result_for_player
from scraping_biwenger.shared.timing import log_timing_debug


def _cooldown(min_ms=300, max_ms=900):
    time.sleep(random.uniform(min_ms / 1000, max_ms / 1000))


def _log_timing(logger, label: str, started_at: float, *, player_slug: str = "") -> None:
    log_timing_debug(logger, label, started_at, player_slug=player_slug)


def _next_player_needs_table(
    players_list: List[Dict[str, str]],
    idx: int,
    *,
    max_players: Optional[int],
    processed: int,
) -> bool:
    if idx >= len(players_list):
        return False
    if max_players and processed >= max_players:
        return False
    next_player = players_list[idx]
    return not bool(next_player.get("href"))


def scrape_all_players_detail(
    logger,
    page: Page,
    players_list: List[Dict[str, str]],
    max_players: Optional[int] = None,
    base_url: str = "https://biwenger.as.com",
    collect_matches: bool = True,
    on_player_payload: Optional[Callable[..., None]] = None,
    on_player_error: Optional[Callable[..., None]] = None,
    on_player_event: Optional[Callable[..., None]] = None,
    stop_requested: Optional[Callable[[], bool]] = None,
    pacing_policy: Optional[PlayerRunPacingPolicy] = None,
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
    pacing_policy = pacing_policy or PlayerRunPacingPolicy(profile="off", enabled=False)

    def record_player_error(
        player: Dict[str, str],
        stage: str,
        message: str,
        *,
        details: Optional[Dict[str, str]] = None,
        emit_failure_event: bool = True,
    ) -> None:
        if on_player_error:
            on_player_error(player=player, stage=stage, message=message, details=details or {})
        if on_player_event and emit_failure_event:
            on_player_event(
                "player_failed",
                player_name=player.get("name", ""),
                player_slug=player.get("slug", ""),
                team=player.get("team", ""),
                rank=player.get("rank"),
                attempt_label=player.get("attempt", "initial"),
                stage=stage,
                message=message,
                **(details or {}),
            )

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
        if stop_requested and stop_requested():
            logger.warning("Stopping player detail loop because circuit breaker has been triggered.")
            break
        player_started_at = time.time()
        if max_players and processed >= max_players:
            logger.info(f"⛔ Reached max_players={max_players}. Stopping early.")
            break

        name = player.get("name", "")
        slug = player.get("slug", "")
        logger.debug("Opening player %s/%s: %s (%s)", idx, len(players_list), name, slug)
        if on_player_event:
            on_player_event(
                "player_started",
                player_name=name,
                player_slug=slug,
                rank=player.get("rank", idx),
                total_players=min(len(players_list), max_players or len(players_list)),
                attempt_label=player.get("attempt", "initial"),
                team=player.get("team", ""),
            )

        def needs_table_return() -> bool:
            return _next_player_needs_table(
                players_list,
                idx,
                max_players=max_players,
                processed=processed,
            )

        with network_action(page, "player_cycle", player_slug=slug, player_name=name, rank=idx):
            # 1) open the player page
            opened = open_player_detail(logger, page, player, base_url=base_url)
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
                if stop_requested and stop_requested():
                    break
                continue
            pacing_policy.apply("after_open", processed=processed)

            try:
                pacing_policy.apply("before_scoring", processed=processed)
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
                    _log_timing(
                        logger,
                        "Back-to-table after scoring-system failure",
                        back_started_at,
                        player_slug=slug,
                    )
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
                if stop_requested and stop_requested():
                    break
                continue

            # 2) scrape left-panel stats
            detail = None
            player_match_rows: List[Dict[str, str]] = []
            player_value_history_rows: List[Dict[str, str]] = []
            try:
                detail_started_at = time.time()
                detail = scrape_player_detail(page, logger=logger)
                _log_timing(logger, "Detail scrape", detail_started_at, player_slug=slug)
                detail.update(
                    {
                        "name": name,
                        "slug": slug,
                        "href": player.get("href", ""),
                        "scoring_system": scoring_system,
                    }
                )
                player_detail_rows.append(detail)
                processed += 1
                logger.debug(
                    "Stats scraped for %s: %s",
                    name,
                    {
                        k: detail.get(k)
                        for k in [
                            "points",
                            "value",
                            "matches_played",
                            "average",
                            "market_purchases_pct",
                            "market_sales_pct",
                        ]
                    },
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
                    rows = (
                        with_retries(
                            lambda: scrape_player_matches(page, logger=logger),
                            validate=lambda r: r is not None and len(r) > 0,
                            attempts=2,
                            base_sleep=0.6,
                            logger=logger,
                        )
                        or []
                    )

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
            value_stage_status = "unknown"
            value_retry_reason = ""
            try:
                pacing_policy.apply("before_value", processed=processed)
                value_started_at = time.time()
                value_result = scrape_value_history_result_for_player(
                    page,
                    logger=logger,
                    player_ctx={
                        "player_name": detail.get("player_name", "") or name,
                        "team": detail.get("team", ""),
                        "slug": slug,
                    },
                    timeout=7000,
                )
                value_stage_status = value_result.status
                value_retry_reason = value_result.retry_reason
                if not value_result.dataframe.empty:
                    player_value_history_rows = value_result.dataframe.to_dict(orient="records")
                    value_history_rows.extend(player_value_history_rows)
                    logger.debug("Value history captured for %s: %s rows", name, len(value_result.dataframe))
                else:
                    logger.debug("Value history empty for %s", name)
                _log_timing(logger, "Value history scrape", value_started_at, player_slug=slug)
            except Exception as e:
                logger.warning(f"⚠️ Failed to scrape value history for {name}: {e}")
                value_stage_status = "unknown"
                value_retry_reason = "scrape_value_history_exception"

            player["_value_stage_status"] = value_stage_status
            player["_value_retry_reason"] = value_retry_reason

            stage_label = "ok"
            if len(player_match_rows) > 0 and len(player_value_history_rows) == 0:
                stage_label = "value_incomplete"
                player["_stage_status"] = stage_label
                details = {
                    "reason": value_retry_reason or "values_missing_after_matches",
                    "match_rows": len(player_match_rows),
                    "value_rows": len(player_value_history_rows),
                    "stats_rows": 1,
                    "scoring_system": scoring_system,
                }
                record_player_error(
                    player,
                    "value_history_incomplete",
                    (
                        f"Value history incomplete: reason={details['reason']} "
                        f"matches={details['match_rows']} values={details['value_rows']}"
                    ),
                    details=details,
                    emit_failure_event=False,
                )
                if on_player_event:
                    on_player_event(
                        "player_value_incomplete",
                        player_name=detail.get("player_name", "") or name,
                        player_slug=slug,
                        team=detail.get("team", ""),
                        rank=player.get("rank", idx),
                        attempt_label=player.get("attempt", "initial"),
                        stage="value_history_incomplete",
                        reason=details["reason"],
                        stats_rows=1,
                        match_rows=len(player_match_rows),
                        value_rows=len(player_value_history_rows),
                        scoring_system=scoring_system,
                    )
            else:
                player["_stage_status"] = stage_label

            if on_player_payload:
                on_player_payload(
                    player=player,
                    detail_rows=[detail],
                    match_rows=player_match_rows,
                    value_history_rows=player_value_history_rows,
                    processed_count=processed,
                )
            if on_player_event:
                note = ""
                if detail.get("matches_played", 0) == 0 and not player_match_rows:
                    note = "no_match_history"
                on_player_event(
                    "player_finished",
                    player_name=detail.get("player_name", "") or name,
                    player_slug=slug,
                    team=detail.get("team", ""),
                    rank=player.get("rank", idx),
                    attempt_label=player.get("attempt", "initial"),
                    processed_count=processed,
                    total_players=min(len(players_list), max_players or len(players_list)),
                    scoring_system=scoring_system,
                    stats_rows=1,
                    match_rows=len(player_match_rows),
                    value_rows=len(player_value_history_rows),
                    stage=stage_label,
                    note=note,
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
            pacing_policy.apply("after_player", processed=processed)
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
                stage=stage_label,
            )
            pacing_policy.apply("every_10_players", processed=processed)
            pacing_policy.apply("every_50_players", processed=processed)

    logger.info(
        f"🏁 Done. Players processed: {processed}. "
        f"Detail rows: {len(player_detail_rows)}, Match rows: {len(match_rows)}"
    )

    return player_detail_rows, match_rows, value_history_rows
