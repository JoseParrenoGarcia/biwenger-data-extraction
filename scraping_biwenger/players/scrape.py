from scraping_biwenger.players.circuit_breaker import PlayerRunCircuitBreaker
from scraping_biwenger.players.detail_loop import scrape_all_players_detail
from scraping_biwenger.players.discover import extract_all_player_names
from scraping_biwenger.players.network_telemetry import network_action
from scraping_biwenger.players.pacing import build_pacing_policy
from scraping_biwenger.shared.auth import dismiss_app_popups_if_present
from scraping_biwenger.shared.navigation import click_tab_in_horizontal_main_menu
from scraping_biwenger.shared.timing import _rand_sleep

RETRYABLE_DETAIL_ERROR_STAGES = {
    "open_player",
    "select_scoring_system",
    "scrape_detail",
}
VALUE_RETRY_STAGE = "value_history_incomplete"


def select_player_table_layout(page, logger=None) -> None:
    """
    Navigate to the players tab and select table layout.
    """
    click_tab_in_horizontal_main_menu(page, "players", logger=logger)
    dismiss_app_popups_if_present(page, logger=logger)
    _rand_sleep(0.5, 1.5)

    try:
        with network_action(page, "select_players_table_layout"):
            page.get_by_role("button", name="Table").click()
        if logger:
            logger.info("Selected players table layout.")
    except Exception:
        if logger:
            logger.info("Players table layout button was not clicked; scraper will wait for rows.")
    _rand_sleep(0.5, 1.5)


def prepare_players_table(page, logger=None) -> None:
    with network_action(page, "players_page_setup"):
        select_player_table_layout(page, logger=logger)


def scrape_player_rows(
    page,
    logger,
    *,
    max_pages: int | None = None,
    max_players_detail: int | None = None,
    player_slug: str | None = None,
    selected_players_override: list[dict] | None = None,
    start_from_slug: str | None = None,
    start_from_href: str | None = None,
    start_from_rank: int | None = None,
    retry_top_players: int = 0,
    on_player_payload=None,
    on_player_error=None,
    on_players_selected=None,
    on_event=None,
    on_run_state=None,
    pacing_profile: str = "normal",
    circuit_breaker_consecutive_failures: int = 4,
    circuit_breaker_window_size: int = 10,
    circuit_breaker_window_failures: int = 8,
) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    """
    Scrape player discovery rows plus detail, match, and value-history rows.
    """
    if selected_players_override is not None:
        players_list = [dict(player) for player in selected_players_override]
        selected_players = [dict(player) for player in selected_players_override]
        if logger:
            logger.info(
                "Using preselected player list override with %s players; skipping player-list discovery.",
                len(selected_players),
            )
    elif player_slug:
        slug = player_slug.strip().strip("/")
        if "/" in slug:
            slug = slug.rstrip("/").split("/")[-1]
        selected_players = [
            {
                "name": slug,
                "slug": slug,
                "href": f"/la-liga/players/{slug}",
                "open_by_href_only": True,
                "rank": 1,
                "attempt": "initial",
            }
        ]
        if logger:
            logger.info(
                "Targeting one player by slug '%s'; skipping player-list discovery.",
                slug,
            )
        players_list = selected_players
    else:
        prepare_players_table(page, logger=logger)

        with network_action(page, "players_discovery"):
            players_list = extract_all_player_names(
                logger=logger,
                page=page,
                max_pages=max_pages,
                max_players=max_players_detail,
            )
        if max_players_detail is not None:
            selected_players = players_list[:max_players_detail]
        else:
            selected_players = players_list
        selected_players = [
            {
                **player,
                "rank": idx,
                "attempt": "initial",
            }
            for idx, player in enumerate(selected_players, start=1)
        ]

        if logger:
            logger.info(
                "Discovered %s players and selected %s for detail scraping.",
                len(players_list),
                len(selected_players),
            )

    if on_players_selected and selected_players:
        on_players_selected(selected_players)

    selected_players = _filter_selected_players(
        selected_players,
        start_from_slug=start_from_slug,
        start_from_href=start_from_href,
        start_from_rank=start_from_rank,
    )
    if (start_from_slug or start_from_href or start_from_rank is not None) and logger:
        logger.info(
            "Applied manual start filter; %s players remain in the selected list.",
            len(selected_players),
        )

    if not selected_players:
        return players_list, [], [], []

    retry_candidates: dict[str, dict] = {}
    value_retry_candidates: dict[str, dict] = {}
    value_retry_failures: set[str] = set()
    pacing_policy = build_pacing_policy(
        pacing_profile,
        targeted_player=bool(player_slug and selected_players_override is None),
    )
    circuit_breaker = PlayerRunCircuitBreaker(
        consecutive_failures_threshold=circuit_breaker_consecutive_failures,
        window_size=circuit_breaker_window_size,
        window_failures_threshold=circuit_breaker_window_failures,
    )

    def player_retry_key(player: dict) -> str:
        return player.get("slug") or player.get("href") or player.get("name", "")

    def should_retry_player(player: dict, stage: str) -> bool:
        if retry_top_players <= 0:
            return False
        if player.get("attempt") != "initial":
            return False
        if stage not in RETRYABLE_DETAIL_ERROR_STAGES:
            return False
        rank = player.get("rank")
        if not isinstance(rank, int) or rank > retry_top_players:
            return False
        return True

    def should_retry_value_history(player: dict, stage: str) -> bool:
        if stage != VALUE_RETRY_STAGE:
            return False
        if player.get("attempt") == "value_retry":
            return False
        return True

    def handle_player_error(*, player, stage, message, details=None) -> None:
        if on_player_error:
            on_player_error(player=player, stage=stage, message=message, details=details or {})
        breaker_triggered = circuit_breaker.record_failure(
            stage=stage,
            message=message,
            player_slug=player.get("slug", ""),
            rank=player.get("rank"),
        )
        key = player_retry_key(player)
        if player.get("attempt") == "value_retry" and key:
            value_retry_failures.add(key)
        if logger and stage in RETRYABLE_DETAIL_ERROR_STAGES and not circuit_breaker.triggered:
            if circuit_breaker.recent_failure_count >= max(
                1, circuit_breaker.window_failures_threshold - 3
            ) or circuit_breaker.consecutive_failures >= max(1, circuit_breaker.consecutive_failures_threshold - 1):
                logger.warning(
                    "Breaker warning: %s relevant failures in last %s players (consecutive=%s).",
                    circuit_breaker.recent_failure_count,
                    circuit_breaker.window_size,
                    circuit_breaker.consecutive_failures,
                )
        if breaker_triggered:
            if logger:
                logger.warning(
                    "Circuit breaker triggered at rank=%s slug=%s stage=%s after %s consecutive failures "
                    "and %s failures in the last %s players.",
                    player.get("rank"),
                    player.get("slug", ""),
                    stage,
                    circuit_breaker.consecutive_failures,
                    circuit_breaker.recent_failure_count,
                    circuit_breaker.window_size,
                )
            if on_event:
                on_event(
                    "circuit_breaker_triggered",
                    player_name=player.get("name", ""),
                    player_slug=player.get("slug", ""),
                    rank=player.get("rank"),
                    stage=stage,
                    message=message,
                    consecutive_failures=circuit_breaker.consecutive_failures,
                    recent_failure_count=circuit_breaker.recent_failure_count,
                    window_size=circuit_breaker.window_size,
                )
        if not should_retry_player(player, stage):
            if should_retry_value_history(player, stage):
                if not key or key in value_retry_candidates:
                    return
                value_retry_candidates[key] = {
                    **player,
                    "attempt": "value_retry",
                    "open_by_href_only": True,
                    "retry_stage": stage,
                }
                if logger:
                    logger.warning(
                        "Queued player for value retry: %s rank=%s reason=%s matches=%s values=%s",
                        player.get("name", ""),
                        player.get("rank"),
                        (details or {}).get("reason", ""),
                        (details or {}).get("match_rows", 0),
                        (details or {}).get("value_rows", 0),
                    )
                if on_event:
                    on_event(
                        "player_value_retry_queued",
                        player_name=player.get("name", ""),
                        player_slug=player.get("slug", ""),
                        rank=player.get("rank"),
                        reason=(details or {}).get("reason", ""),
                        match_rows=(details or {}).get("match_rows", 0),
                        value_rows=(details or {}).get("value_rows", 0),
                    )
            return
        if not key or key in retry_candidates:
            return
        retry_candidates[key] = {
            **player,
            "attempt": "retry",
            "open_by_href_only": True,
            "retry_stage": stage,
        }
        if logger:
            logger.info(
                "Queued player for retry: %s rank=%s stage=%s",
                player.get("name", ""),
                player.get("rank"),
                stage,
            )
        if on_event:
            on_event(
                "retry_queued",
                player_name=player.get("name", ""),
                player_slug=player.get("slug", ""),
                rank=player.get("rank"),
                stage=stage,
            )

    player_detail_rows, match_rows, value_history_rows = scrape_all_players_detail(
        logger,
        page,
        selected_players,
        max_players=max_players_detail,
        collect_matches=True,
        on_player_payload=on_player_payload,
        on_player_error=handle_player_error,
        on_player_event=_wrap_player_event(on_event, circuit_breaker),
        stop_requested=lambda: circuit_breaker.triggered,
        pacing_policy=pacing_policy,
    )

    if on_run_state:
        on_run_state(
            {
                "termination_reason": "circuit_breaker" if circuit_breaker.triggered else "completed",
                **circuit_breaker.state_payload(),
            }
        )

    if circuit_breaker.triggered:
        return players_list, player_detail_rows, match_rows, value_history_rows

    if retry_candidates:
        retry_players = list(retry_candidates.values())
        if logger:
            logger.info(
                "Starting retry pass for %s failed top-%s players.",
                len(retry_players),
                retry_top_players,
            )
        if on_event:
            on_event(
                "retry_pass_started",
                retry_count=len(retry_players),
                retry_top_players=retry_top_players,
            )
        retry_detail_rows, retry_match_rows, retry_value_history_rows = scrape_all_players_detail(
            logger,
            page,
            retry_players,
            max_players=len(retry_players),
            collect_matches=True,
            on_player_payload=on_player_payload,
            on_player_error=handle_player_error,
            on_player_event=on_event,
        )
        player_detail_rows.extend(retry_detail_rows)
        match_rows.extend(retry_match_rows)
        value_history_rows.extend(retry_value_history_rows)
        if logger:
            recovered = len(retry_detail_rows)
            failed = max(0, len(retry_players) - recovered)
            logger.info(
                "Retry pass completed: %s recovered players, %s still failed.",
                recovered,
                failed,
            )
        if on_event:
            on_event(
                "retry_pass_finished",
                retry_count=len(retry_players),
                recovered_count=recovered,
                failed_count=failed,
            )

    if value_retry_candidates:
        value_retry_players = list(value_retry_candidates.values())
        if logger:
            logger.info(
                "Starting value retry pass for %s queued players.",
                len(value_retry_players),
            )
        if on_event:
            on_event(
                "value_retry_pass_started",
                retry_count=len(value_retry_players),
            )
        value_retry_failures.clear()
        value_retry_detail_rows, value_retry_match_rows, value_retry_history_rows = scrape_all_players_detail(
            logger,
            page,
            value_retry_players,
            max_players=len(value_retry_players),
            collect_matches=True,
            on_player_payload=on_player_payload,
            on_player_error=handle_player_error,
            on_player_event=on_event,
        )
        player_detail_rows.extend(value_retry_detail_rows)
        match_rows.extend(value_retry_match_rows)
        value_history_rows.extend(value_retry_history_rows)
        recovered = max(0, len(value_retry_players) - len(value_retry_failures))
        failed = len(value_retry_failures)
        if logger:
            logger.info(
                "Value retry pass completed: %s recovered, %s still incomplete.",
                recovered,
                failed,
            )
        if on_event:
            on_event(
                "value_retry_pass_finished",
                retry_count=len(value_retry_players),
                recovered_count=recovered,
                failed_count=failed,
            )

    return players_list, player_detail_rows, match_rows, value_history_rows


def _wrap_player_event(on_event, circuit_breaker: PlayerRunCircuitBreaker):
    def emit(event_type, **payload):
        if event_type == "player_finished":
            circuit_breaker.record_success()
        if on_event is not None:
            on_event(event_type, **payload)

    return emit


def _filter_selected_players(
    selected_players: list[dict],
    *,
    start_from_slug: str | None = None,
    start_from_href: str | None = None,
    start_from_rank: int | None = None,
) -> list[dict]:
    if start_from_slug is None and start_from_href is None and start_from_rank is None:
        return selected_players

    target_index = None
    if start_from_slug is not None:
        target_slug = start_from_slug.strip().strip("/").split("/")[-1]
        for idx, player in enumerate(selected_players):
            if str(player.get("slug") or "").strip() == target_slug:
                target_index = idx
                break
        if target_index is None:
            raise ValueError(f"Could not find start-from slug '{target_slug}' in the selected player list.")
    elif start_from_href is not None:
        target_href = start_from_href.strip()
        for idx, player in enumerate(selected_players):
            if str(player.get("href") or "").strip() == target_href:
                target_index = idx
                break
        if target_index is None:
            raise ValueError(f"Could not find start-from href '{target_href}' in the selected player list.")
    else:
        for idx, player in enumerate(selected_players):
            if player.get("rank") == start_from_rank:
                target_index = idx
                break
        if target_index is None:
            raise ValueError(f"Could not find start-from rank '{start_from_rank}' in the selected player list.")

    return selected_players[target_index:]
