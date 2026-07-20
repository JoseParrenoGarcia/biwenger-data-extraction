from config_logging import get_logger
import pandas as pd

from scraping_biwenger.players.checkpoints import (
    DEFAULT_CHECKPOINT_ROOT,
    PlayerRunCheckpoint,
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
from scraping_biwenger.shared.config import load_biwenger_credentials


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
    logger = logger or get_logger(
        "ETL_get_player_stats",
        log_file="logs/ETL_get_player_stats.log",
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
    checkpoint_dir: str = DEFAULT_CHECKPOINT_ROOT,
    checkpoint_enabled: bool = True,
    upload_batch_size: int = 10,
    logger=None,
):
    """
    Login to Biwenger, scrape player data, and optionally persist it.
    """
    logger = logger or get_logger(
        "ETL_get_player_stats",
        log_file="logs/ETL_get_player_stats.log",
    )
    logger.info("=" * 70)
    logger.info("Starting ETL: get_player_stats")
    logger.info("=" * 70)

    creds = load_biwenger_credentials(profile="biwenger_player_scraper")
    logger.info("Credentials loaded successfully for profile 'biwenger_player_scraper'.")

    as_of_date = pd.Timestamp.utcnow().date().isoformat()
    checkpoint = None
    if checkpoint_enabled:
        checkpoint = PlayerRunCheckpoint(
            root_dir=checkpoint_dir,
            metadata={
                "pipeline": "get_player_stats",
                "as_of_date": as_of_date,
                "persist_requested": persist,
                "max_pages": max_pages,
                "max_players_detail": max_players_detail,
                "player_slug": player_slug,
                "upload_batch_size": upload_batch_size,
            },
        )
        logger.info("Player run checkpoint enabled: %s", checkpoint.run_dir)
        run_player_pipeline.last_checkpoint_dir = str(checkpoint.run_dir)
    else:
        logger.info("Player run checkpoint disabled.")
        run_player_pipeline.last_checkpoint_dir = None

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
            logger.info(
                "Checkpointed player %s: %s stats rows, %s match rows, %s value rows.",
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
