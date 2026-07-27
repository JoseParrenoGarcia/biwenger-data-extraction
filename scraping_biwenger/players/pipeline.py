import logging
import time
from pathlib import Path

import pandas as pd

from config_logging import get_logger
from scraping_biwenger.players.checkpoints import (
    DEFAULT_CHECKPOINT_ROOT,
    PlayerRunCheckpoint,
    build_resume_candidates,
    cleanup_old_player_runs,
    read_player_checkpoint,
    read_selected_players,
    write_resume_candidates,
)
from scraping_biwenger.players.persist import persist_player_outputs
from scraping_biwenger.players.run_events import build_event_emitter
from scraping_biwenger.players.scrape import scrape_player_rows
from scraping_biwenger.players.terminal_ui import PlayerRunTerminalUI
from scraping_biwenger.players.transform import (
    PLAYER_MATCHES_COLUMNS,
    PLAYER_STATS_COLUMNS,
    PLAYER_VALUE_COLUMNS,
    transform_player_outputs,
)
from scraping_biwenger.shared.auth import perform_login
from scraping_biwenger.shared.browser_session import start_browser_accept_cookies
from scraping_biwenger.shared.config import (
    PLAYER_SCRAPER_PROFILE,
    assert_biwenger_profile_allowed,
    load_biwenger_credentials,
)


def _concat_frames(frames: list[pd.DataFrame], columns: list[str]) -> pd.DataFrame:
    frames = [frame for frame in frames if frame is not None and not frame.empty]
    if not frames:
        return pd.DataFrame(columns=columns)
    return pd.concat(frames, ignore_index=True)


def scrape_players_snapshot(
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
    pacing_profile: str = "normal",
    circuit_breaker_consecutive_failures: int = 4,
    circuit_breaker_window_size: int = 10,
    circuit_breaker_window_failures: int = 8,
    as_of_date: str | None = None,
    on_player_payload=None,
    on_player_error=None,
    on_players_selected=None,
    on_event=None,
    on_run_state=None,
):
    """
    Scrape and normalize player stats, matches, and value history from a logged-in page.
    """
    players_list, player_detail_rows, match_rows, value_history_rows = scrape_player_rows(
        page,
        logger,
        max_pages=max_pages,
        max_players_detail=max_players_detail,
        player_slug=player_slug,
        selected_players_override=selected_players_override,
        start_from_slug=start_from_slug,
        start_from_href=start_from_href,
        start_from_rank=start_from_rank,
        retry_top_players=retry_top_players,
        pacing_profile=pacing_profile,
        circuit_breaker_consecutive_failures=circuit_breaker_consecutive_failures,
        circuit_breaker_window_size=circuit_breaker_window_size,
        circuit_breaker_window_failures=circuit_breaker_window_failures,
        on_player_payload=on_player_payload,
        on_player_error=on_player_error,
        on_players_selected=on_players_selected,
        on_event=on_event,
        on_run_state=on_run_state,
    )
    if not players_list:
        logger.warning("No players extracted; returning empty player payloads.")

    stats_df, matches_df, value_history_df = transform_player_outputs(
        player_detail_rows,
        match_rows,
        value_history_rows,
        as_of_date=as_of_date,
    )
    logger.info(
        "Transformed player payloads: %s stats rows, %s match rows, %s value rows.",
        len(stats_df),
        len(matches_df),
        len(value_history_df),
    )
    return stats_df, matches_df, value_history_df


def upload_player_checkpoint(run_dir: str, *, logger=None, supabase=None):
    started_at = time.perf_counter()
    if logger is None:
        run_path = Path(run_dir)
        log_file = run_path / "upload.log" if run_path.is_dir() else Path("logs/ETL_get_player_stats.log")
        logger = get_logger(
            "ETL_get_player_stats",
            log_file=str(log_file),
            reset_handlers=True,
        )
    payload = read_player_checkpoint(run_dir)
    logger.info(
        "Uploading player checkpoint from %s: %s stats rows, %s match rows, %s value rows.",
        run_dir,
        len(payload.stats_df),
        len(payload.matches_df),
        len(payload.value_history_df),
    )
    persist_player_outputs(
        payload.stats_df,
        payload.matches_df,
        payload.value_history_df,
        logger=logger,
        supabase=supabase,
    )
    logger.info("Checkpoint upload completed for %s in %.2fs.", run_dir, time.perf_counter() - started_at)
    return payload.stats_df, payload.matches_df, payload.value_history_df


def run_player_pipeline(
    *,
    headless: bool = True,
    persist: bool = True,
    max_pages: int = 100,
    max_players_detail: int = 1_000,
    player_slug: str | None = None,
    start_from_slug: str | None = None,
    start_from_href: str | None = None,
    start_from_rank: int | None = None,
    resume_checkpoint: str | None = None,
    retry_top_players: int = 0,
    checkpoint_dir: str = DEFAULT_CHECKPOINT_ROOT,
    checkpoint_enabled: bool = True,
    upload_batch_size: int = 10,
    pacing_profile: str = "normal",
    circuit_breaker_consecutive_failures: int = 4,
    circuit_breaker_window_size: int = 10,
    circuit_breaker_window_failures: int = 8,
    debug_log: bool = False,
    run_retention_days: int = 7,
    terminal_ui: bool = False,
    logger=None,
):
    """
    Login to Biwenger, scrape player data, and optionally persist it.
    """
    started_at = time.perf_counter()
    as_of_date = pd.Timestamp.utcnow().date().isoformat()
    checkpoint = None
    deleted_old_runs = []
    ui = PlayerRunTerminalUI() if terminal_ui else None
    event_emitter = build_event_emitter(ui.handle_event if ui else None)
    resume_players_override = None
    resume_failed_count = 0
    resume_tail_count = 0
    run_state: dict = {"termination_reason": "completed"}

    if sum(option is not None for option in [start_from_slug, start_from_href, start_from_rank]) > 1:
        raise ValueError("Use at most one of --start-from-slug, --start-from-href, or --start-from-rank.")
    if player_slug and any(option is not None for option in [start_from_slug, start_from_href, start_from_rank]):
        raise ValueError("--player-slug cannot be combined with manual start-from options.")
    if player_slug and resume_checkpoint:
        raise ValueError("--player-slug cannot be combined with --resume-checkpoint.")

    if resume_checkpoint:
        resume_players_override, resume_failed_count, resume_tail_count = _build_resume_players(
            run_dir=resume_checkpoint,
            start_from_slug=start_from_slug,
            start_from_href=start_from_href,
            start_from_rank=start_from_rank,
        )
    if checkpoint_enabled:
        deleted_old_runs = cleanup_old_player_runs(
            checkpoint_dir,
            retention_days=run_retention_days,
        )
        checkpoint = PlayerRunCheckpoint(
            root_dir=checkpoint_dir,
            metadata={
                "pipeline": "get_player_stats",
                "as_of_date": as_of_date,
                "persist_requested": persist,
                "max_pages": max_pages,
                "max_players_detail": max_players_detail,
                "player_slug": player_slug,
                "start_from_slug": start_from_slug,
                "start_from_href": start_from_href,
                "start_from_rank": start_from_rank,
                "resume_checkpoint": resume_checkpoint,
                "retry_top_players": retry_top_players,
                "upload_batch_size": upload_batch_size,
                "pacing_profile": pacing_profile,
                "circuit_breaker_consecutive_failures": circuit_breaker_consecutive_failures,
                "circuit_breaker_window_size": circuit_breaker_window_size,
                "circuit_breaker_window_failures": circuit_breaker_window_failures,
                "debug_log": debug_log,
                "run_retention_days": run_retention_days,
                "terminal_ui": terminal_ui,
            },
        )
        if logger is None:
            logger = get_logger(
                "ETL_get_player_stats",
                log_file=str(checkpoint.run_log_path),
                level=logging.DEBUG if debug_log else logging.INFO,
                file_level=logging.DEBUG if debug_log else logging.INFO,
                console_level=logging.WARNING if terminal_ui else logging.INFO,
                reset_handlers=True,
            )
        logger.info("Player run checkpoint enabled: %s", checkpoint.run_dir)
        run_player_pipeline.last_checkpoint_dir = str(checkpoint.run_dir)
    else:
        logger = logger or get_logger(
            "ETL_get_player_stats",
            log_file="logs/ETL_get_player_stats.log",
            level=logging.DEBUG if debug_log else logging.INFO,
            file_level=logging.DEBUG if debug_log else logging.INFO,
            console_level=logging.WARNING if terminal_ui else logging.INFO,
            reset_handlers=True,
        )
        logger.info("Player run checkpoint disabled.")
        run_player_pipeline.last_checkpoint_dir = None

    logger.info("=" * 70)
    logger.info("Starting ETL: get_player_stats")
    logger.info("=" * 70)
    if checkpoint_enabled and deleted_old_runs:
        logger.info(
            "Cleaned up %s old player run artifact directories older than %s days: %s",
            len(deleted_old_runs),
            run_retention_days,
            ", ".join(path.name for path in deleted_old_runs),
        )
    elif checkpoint_enabled:
        logger.info("No old player run artifacts to clean up older than %s days.", run_retention_days)

    assert_biwenger_profile_allowed(use_case="player_scraping", profile=PLAYER_SCRAPER_PROFILE)
    creds = load_biwenger_credentials(profile=PLAYER_SCRAPER_PROFILE)
    logger.info("Credentials loaded successfully for profile '%s'.", PLAYER_SCRAPER_PROFILE)
    event_emitter.emit(
        "run_started",
        run_id=checkpoint.run_id if checkpoint else "",
        run_dir=str(checkpoint.run_dir) if checkpoint else "",
        dry_run=not persist,
        headed=not headless,
        max_pages=max_pages,
        max_players_detail=max_players_detail,
        retry_top_players=retry_top_players,
        upload_batch_size=upload_batch_size,
        pacing_profile=pacing_profile,
        circuit_breaker_consecutive_failures=circuit_breaker_consecutive_failures,
        circuit_breaker_window_size=circuit_breaker_window_size,
        circuit_breaker_window_failures=circuit_breaker_window_failures,
    )

    if checkpoint and resume_checkpoint:
        checkpoint.update_metadata(
            {
                "resumed_from_run_dir": resume_checkpoint,
                "resume_mode": "checkpoint",
                "resume_failed_count": resume_failed_count,
                "resume_tail_count": resume_tail_count,
            }
        )
    elif checkpoint and any(option is not None for option in [start_from_slug, start_from_href, start_from_rank]):
        checkpoint.update_metadata(
            {
                "resume_mode": "manual_start",
                "start_from_slug": start_from_slug,
                "start_from_href": start_from_href,
                "start_from_rank": start_from_rank,
            }
        )

    upload_batch_size = max(1, upload_batch_size)
    batch_number = 0
    batch_upload_failed = False
    pending_stats: list[pd.DataFrame] = []
    pending_matches: list[pd.DataFrame] = []
    pending_values: list[pd.DataFrame] = []

    def flush_upload_buffer(reason: str) -> None:
        nonlocal batch_number, batch_upload_failed, pending_stats, pending_matches, pending_values
        stats_df = _concat_frames(pending_stats, PLAYER_STATS_COLUMNS)
        matches_df = _concat_frames(pending_matches, PLAYER_MATCHES_COLUMNS)
        value_history_df = _concat_frames(pending_values, PLAYER_VALUE_COLUMNS)
        total_rows = len(stats_df) + len(matches_df) + len(value_history_df)
        if not total_rows:
            return

        batch_number += 1
        event_emitter.emit(
            "batch_upload_started",
            batch_number=batch_number,
            reason=reason,
            stats_rows=len(stats_df),
            match_rows=len(matches_df),
            value_rows=len(value_history_df),
        )
        logger.info(
            "Uploading player batch %s (%s): %s stats rows, %s match rows, %s value rows.",
            batch_number,
            reason,
            len(stats_df),
            len(matches_df),
            len(value_history_df),
        )
        try:
            persist_player_outputs(
                stats_df,
                matches_df,
                value_history_df,
                logger=logger,
            )
            logger.info("Player batch %s upload completed.", batch_number)
            event_emitter.emit(
                "batch_upload_finished",
                batch_number=batch_number,
                stats_rows=len(stats_df),
                match_rows=len(matches_df),
                value_rows=len(value_history_df),
            )
        except Exception as exc:
            batch_upload_failed = True
            logger.exception("Player batch %s upload failed; continuing with local checkpoints.", batch_number)
            event_emitter.emit(
                "batch_upload_failed",
                batch_number=batch_number,
                stats_rows=len(stats_df),
                match_rows=len(matches_df),
                value_rows=len(value_history_df),
                message=str(exc),
            )
            if checkpoint:
                checkpoint.append_upload_error(
                    batch_number=batch_number,
                    stats_rows=len(stats_df),
                    match_rows=len(matches_df),
                    value_rows=len(value_history_df),
                    message=str(exc),
                )
        finally:
            pending_stats = []
            pending_matches = []
            pending_values = []

    def replay_checkpoint_after_batch_failure() -> None:
        if not checkpoint or not batch_upload_failed:
            return

        logger.warning(
            "One or more player batch uploads failed; replaying full checkpoint from %s.",
            checkpoint.run_dir,
        )
        try:
            upload_player_checkpoint(str(checkpoint.run_dir), logger=logger)
        except Exception:
            logger.exception(
                "Full checkpoint replay failed. Retry manually with: "
                ".venv/bin/python -m scraping_biwenger.get_player_stats --upload-checkpoint %s",
                checkpoint.run_dir,
            )
            raise

    def on_player_payload(*, player, detail_rows, match_rows, value_history_rows, processed_count) -> None:
        stats_df, matches_df, value_history_df = transform_player_outputs(
            detail_rows,
            match_rows,
            value_history_rows,
            as_of_date=as_of_date,
        )
        if checkpoint:
            counts = checkpoint.append_payload(
                player=player,
                stats_df=stats_df,
                matches_df=matches_df,
                value_history_df=value_history_df,
            )
            player["_checkpoint_status"] = "ok"
            player["_checkpoint_counts"] = counts
            logger.debug(
                "Checkpointed player %s | stats=%s matches=%s values=%s",
                player.get("slug") or player.get("name"),
                counts["stats"],
                counts["matches"],
                counts["values"],
            )
            event_emitter.emit(
                "checkpoint_written",
                player_name=player.get("name", ""),
                player_slug=player.get("slug", ""),
                stats_rows=counts["stats"],
                match_rows=counts["matches"],
                value_rows=counts["values"],
                processed_count=processed_count,
            )

        if persist and checkpoint:
            pending_stats.append(stats_df)
            pending_matches.append(matches_df)
            pending_values.append(value_history_df)
            if processed_count % upload_batch_size == 0:
                flush_upload_buffer(f"{processed_count} processed players")

    def on_player_error(*, player, stage, message, details=None) -> None:
        if checkpoint:
            checkpoint.append_player_error(player=player, stage=stage, message=message, details=details or {})

    def on_players_selected(players: list[dict]) -> None:
        if not checkpoint:
            return
        checkpoint.write_selected_players(players)
        checkpoint.update_metadata(
            {
                "selected_player_count": len(players),
                "selected_manifest_written": True,
            }
        )
        logger.info("Wrote selected player manifest with %s players.", len(players))

    def on_run_state(state: dict) -> None:
        run_state.update(state)

    pw, browser, context, page = start_browser_accept_cookies(
        headless=headless,
        logger=logger,
    )
    logger.info("Browser session started.")

    try:
        perform_login(page, creds["email"], creds["password"], logger=logger)
        stats_df, matches_df, value_history_df = scrape_players_snapshot(
            page,
            logger,
            max_pages=max_pages,
            max_players_detail=max_players_detail,
            player_slug=player_slug,
            selected_players_override=resume_players_override,
            start_from_slug=start_from_slug,
            start_from_href=start_from_href,
            start_from_rank=start_from_rank,
            retry_top_players=retry_top_players,
            pacing_profile=pacing_profile,
            circuit_breaker_consecutive_failures=circuit_breaker_consecutive_failures,
            circuit_breaker_window_size=circuit_breaker_window_size,
            circuit_breaker_window_failures=circuit_breaker_window_failures,
            as_of_date=as_of_date,
            on_player_payload=on_player_payload if checkpoint else None,
            on_player_error=on_player_error if checkpoint else None,
            on_players_selected=on_players_selected if checkpoint else None,
            on_event=event_emitter.emit,
            on_run_state=on_run_state,
        )

        if checkpoint and run_state.get("termination_reason") == "circuit_breaker":
            candidates, successful_count, failed_count, untouched_count = write_resume_candidates(checkpoint.run_dir)
            checkpoint.update_metadata(
                {
                    **run_state,
                    "successful_player_count": successful_count,
                    "failed_player_count": failed_count,
                    "untouched_tail_count": untouched_count,
                    "resume_candidate_count": len(candidates),
                }
            )
            logger.warning(
                "Circuit breaker stopped the player run at rank=%s slug=%s stage=%s. "
                "Successful=%s failed=%s untouched_tail=%s resume_candidates=%s. "
                "Resume with: .venv/bin/python -m scraping_biwenger.get_player_stats --resume-checkpoint %s",
                run_state.get("circuit_breaker_rank"),
                run_state.get("circuit_breaker_player_slug", ""),
                run_state.get("circuit_breaker_stage", ""),
                successful_count,
                failed_count,
                untouched_count,
                len(candidates),
                checkpoint.run_dir,
            )

        if persist and checkpoint:
            flush_upload_buffer("final buffered rows")
            replay_checkpoint_after_batch_failure()
        elif persist:
            persist_player_outputs(
                stats_df,
                matches_df,
                value_history_df,
                logger=logger,
            )
        else:
            logger.info("Skipping Supabase persistence for player dry run.")

        duration_s = time.perf_counter() - started_at
        logger.info("Total player run time: %.2fs", duration_s)
        summary_prefix = "aborted" if run_state.get("termination_reason") == "circuit_breaker" else "done"
        event_emitter.emit(
            "run_finished",
            summary=(
                f"{summary_prefix} stats={len(stats_df)} matches={len(matches_df)} "
                f"values={len(value_history_df)} time={duration_s:.2f}s"
            ),
            stats_rows=len(stats_df),
            match_rows=len(matches_df),
            value_rows=len(value_history_df),
            duration_s=duration_s,
            termination_reason=run_state.get("termination_reason", "completed"),
        )
        return stats_df, matches_df, value_history_df
    finally:
        if ui:
            ui.close()
        try:
            context.close()
        except Exception:
            pass
        try:
            browser.close()
        except Exception:
            pass
        try:
            pw.stop()
        except Exception:
            pass


def _build_resume_players(
    *,
    run_dir: str,
    start_from_slug: str | None = None,
    start_from_href: str | None = None,
    start_from_rank: int | None = None,
) -> tuple[list[dict], int, int]:
    selected_players = read_selected_players(run_dir)
    if not selected_players:
        if any(option is not None for option in [start_from_slug, start_from_href, start_from_rank]):
            raise ValueError(
                "Automatic resume is unavailable for this checkpoint because selected_players.jsonl is missing. "
                "Older checkpoints must be resumed manually from an explicit start point using a normal scraping run."
            )
        raise ValueError(
            "Automatic resume requires selected_players.jsonl in the checkpoint run directory. "
            "Older checkpoints must be resumed manually from an explicit start point."
        )

    candidates, _, failed_count, tail_count = build_resume_candidates(run_dir)
    resume_players = []
    for player in candidates:
        attempt = "resume_retry" if player.get("resume_reason") == "failed" else "resume_tail"
        resume_players.append(
            {
                **player,
                "attempt": attempt,
                "failure_stage": player.get("last_failure_stage"),
            }
        )
    if start_from_slug or start_from_href or start_from_rank is not None:
        from scraping_biwenger.players.scrape import _filter_selected_players

        resume_players = _filter_selected_players(
            resume_players,
            start_from_slug=start_from_slug,
            start_from_href=start_from_href,
            start_from_rank=start_from_rank,
        )

    return resume_players, failed_count, tail_count
