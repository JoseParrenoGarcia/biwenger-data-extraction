import logging
from pathlib import Path

import pandas as pd

from config_logging import get_logger
from scraping_biwenger.players.checkpoints import (
    DEFAULT_CHECKPOINT_ROOT,
    PlayerRunCheckpoint,
    cleanup_old_player_runs,
    read_player_checkpoint,
)
from scraping_biwenger.players.persist import persist_player_outputs
from scraping_biwenger.players.scrape import scrape_player_rows
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
    retry_top_players: int = 0,
    as_of_date: str | None = None,
    on_player_payload=None,
    on_player_error=None,
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
        retry_top_players=retry_top_players,
        on_player_payload=on_player_payload,
        on_player_error=on_player_error,
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
    logger.info("Checkpoint upload completed for %s.", run_dir)
    return payload.stats_df, payload.matches_df, payload.value_history_df


def run_player_pipeline(
    *,
    headless: bool = True,
    persist: bool = True,
    max_pages: int = 100,
    max_players_detail: int = 1_000,
    player_slug: str | None = None,
    retry_top_players: int = 0,
    checkpoint_dir: str = DEFAULT_CHECKPOINT_ROOT,
    checkpoint_enabled: bool = True,
    upload_batch_size: int = 10,
    debug_log: bool = False,
    run_retention_days: int = 7,
    logger=None,
):
    """
    Login to Biwenger, scrape player data, and optionally persist it.
    """
    as_of_date = pd.Timestamp.utcnow().date().isoformat()
    checkpoint = None
    deleted_old_runs = []
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
                "retry_top_players": retry_top_players,
                "upload_batch_size": upload_batch_size,
                "debug_log": debug_log,
                "run_retention_days": run_retention_days,
            },
        )
        if logger is None:
            logger = get_logger(
                "ETL_get_player_stats",
                log_file=str(checkpoint.run_log_path),
                level=logging.DEBUG if debug_log else logging.INFO,
                file_level=logging.DEBUG if debug_log else logging.INFO,
                console_level=logging.INFO,
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
            console_level=logging.INFO,
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
        except Exception as exc:
            batch_upload_failed = True
            logger.exception("Player batch %s upload failed; continuing with local checkpoints.", batch_number)
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

        if persist and checkpoint:
            pending_stats.append(stats_df)
            pending_matches.append(matches_df)
            pending_values.append(value_history_df)
            if processed_count % upload_batch_size == 0:
                flush_upload_buffer(f"{processed_count} processed players")

    def on_player_error(*, player, stage, message) -> None:
        if checkpoint:
            checkpoint.append_player_error(player=player, stage=stage, message=message)

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
            retry_top_players=retry_top_players,
            as_of_date=as_of_date,
            on_player_payload=on_player_payload if checkpoint else None,
            on_player_error=on_player_error if checkpoint else None,
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

        return stats_df, matches_df, value_history_df
    finally:
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
