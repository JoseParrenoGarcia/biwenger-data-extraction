import argparse

import pandas as pd

from scraping_biwenger.players.checkpoints import DEFAULT_CHECKPOINT_ROOT
from scraping_biwenger.players.pipeline import run_player_pipeline, upload_player_checkpoint


def ETL_get_player_stats(
    max_pages: int = 100,
    max_players_detail: int = 1_000,
    *,
    headless: bool = True,
    persist: bool = True,
    player_slug: str | None = None,
    start_from_slug: str | None = None,
    start_from_href: str | None = None,
    start_from_rank: int | None = None,
    resume_checkpoint: str | None = None,
    retry_top_players: int = 0,
    checkpoint_dir: str = DEFAULT_CHECKPOINT_ROOT,
    checkpoint_enabled: bool = True,
    upload_batch_size: int = 10,
    pacing_profile: str = "human",
    circuit_breaker_consecutive_failures: int = 4,
    circuit_breaker_window_size: int = 10,
    circuit_breaker_window_failures: int = 8,
    debug_log: bool = False,
    run_retention_days: int = 7,
    terminal_ui: bool = False,
):
    """
    Backward-compatible entry point for the player ETL.
    """
    result = run_player_pipeline(
        headless=headless,
        persist=persist,
        max_pages=max_pages,
        max_players_detail=max_players_detail,
        player_slug=player_slug,
        start_from_slug=start_from_slug,
        start_from_href=start_from_href,
        start_from_rank=start_from_rank,
        resume_checkpoint=resume_checkpoint,
        retry_top_players=retry_top_players,
        checkpoint_dir=checkpoint_dir,
        checkpoint_enabled=checkpoint_enabled,
        upload_batch_size=upload_batch_size,
        pacing_profile=pacing_profile,
        circuit_breaker_consecutive_failures=circuit_breaker_consecutive_failures,
        circuit_breaker_window_size=circuit_breaker_window_size,
        circuit_breaker_window_failures=circuit_breaker_window_failures,
        debug_log=debug_log,
        run_retention_days=run_retention_days,
        terminal_ui=terminal_ui,
    )
    ETL_get_player_stats.last_checkpoint_dir = getattr(run_player_pipeline, "last_checkpoint_dir", None)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Biwenger player pipeline.")
    parser.add_argument(
        "command",
        nargs="?",
        choices=["run_scraping_players"],
        help="Legacy optional subcommand kept for scheduled scripts.",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Show Chromium while scraping.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scrape and transform player rows without uploading to Supabase.",
    )
    parser.add_argument(
        "--max-players",
        type=int,
        default=1_000,
        help="Maximum number of player detail pages to scrape.",
    )
    parser.add_argument(
        "--max-player-pages",
        type=int,
        default=100,
        help="Maximum number of player list pages to discover.",
    )
    parser.add_argument(
        "--player-slug",
        help=(
            "Scrape one Biwenger player directly by URL slug, "
            "for example 'moussa-diarra-2'. Skips player-list discovery."
        ),
    )
    parser.add_argument(
        "--start-from-slug", help="Start scraping from this player slug within the selected player list."
    )
    parser.add_argument(
        "--start-from-href", help="Start scraping from this player href within the selected player list."
    )
    parser.add_argument("--start-from-rank", type=int, help="Start scraping from this selected player rank.")
    parser.add_argument(
        "--resume-checkpoint",
        help="Resume unfinished scraping work from a prior player checkpoint run directory.",
    )
    parser.add_argument(
        "--retry-top-players",
        type=int,
        default=0,
        help=(
            "Retry first-pass open/SofaScore/detail failures for players ranked "
            "within the top N selected players. Default 0 disables retries."
        ),
    )
    parser.add_argument(
        "--checkpoint-dir",
        default=DEFAULT_CHECKPOINT_ROOT,
        help="Directory where player run checkpoints are written.",
    )
    parser.add_argument(
        "--no-checkpoint",
        action="store_true",
        help="Disable local checkpoint files for this run.",
    )
    parser.add_argument(
        "--upload-batch-size",
        type=int,
        default=10,
        help="Number of checkpointed players between Supabase upload attempts.",
    )
    parser.add_argument(
        "--pacing-profile",
        choices=["off", "normal", "human", "slow"],
        default="human",
        help=(
            "Human-like pacing profile for multi-player runs. "
            "'human' is the recommended production default; targeted --player-slug runs bypass pacing."
        ),
    )
    parser.add_argument(
        "--circuit-breaker-consecutive-failures",
        type=int,
        default=4,
        help="Stop the main player pass after this many consecutive relevant failures.",
    )
    parser.add_argument(
        "--circuit-breaker-window-size",
        type=int,
        default=10,
        help="Rolling player window size for the circuit breaker failure threshold.",
    )
    parser.add_argument(
        "--circuit-breaker-window-failures",
        type=int,
        default=8,
        help="Relevant failures inside the rolling window that trigger the circuit breaker.",
    )
    parser.add_argument(
        "--debug-log",
        action="store_true",
        help="Include detailed player scrape timing records in the run log.",
    )
    parser.add_argument(
        "--run-retention-days",
        type=int,
        default=7,
        help="Delete player run artifact directories older than this many days before a new scrape run.",
    )
    parser.add_argument(
        "--terminal-ui",
        action="store_true",
        help="Show a live terminal dashboard for manual player runs.",
    )
    parser.add_argument(
        "--upload-checkpoint",
        help="Upload a saved player checkpoint run directory to Supabase and skip Biwenger scraping.",
    )
    return parser.parse_args()


def _print_df(title: str, df: pd.DataFrame, max_rows: int = 20) -> None:
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)
    print(f"Rows: {len(df)}")
    print(f"Columns: {list(df.columns)}")
    if df.empty:
        print("(empty)")
        return
    print(df.head(max_rows).to_string(index=False))


def _print_dry_run_summary(
    stats_df: pd.DataFrame,
    matches_df: pd.DataFrame,
    value_history_df: pd.DataFrame,
    *,
    checkpoint_dir: str | None = None,
    terminal_ui: bool = False,
    max_rows: int = 20,
) -> None:
    print("\nDRY RUN ONLY: no Supabase rows were written.")
    if checkpoint_dir:
        print(f"Checkpoint directory: {checkpoint_dir}")

    if terminal_ui:
        print(f"Summary: {len(stats_df)} stats rows, {len(matches_df)} match rows, {len(value_history_df)} value rows.")
        return

    _print_df("Player Stats - Dry Run", stats_df, max_rows=max_rows)
    _print_df("Player Matches - Dry Run", matches_df, max_rows=20)
    _print_df("Player Value History - Dry Run", value_history_df, max_rows=20)


def main() -> None:
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", None)
    pd.set_option("display.max_colwidth", None)

    args = parse_args()
    if args.upload_checkpoint:
        if args.resume_checkpoint or args.start_from_slug or args.start_from_href or args.start_from_rank is not None:
            raise SystemExit("--upload-checkpoint cannot be combined with resume or manual start-from options.")
        stats_df, matches_df, value_history_df = upload_player_checkpoint(args.upload_checkpoint)
        print(f"\nUploaded checkpoint: {args.upload_checkpoint}")
        print(f"Stats rows: {len(stats_df)}")
        print(f"Match rows: {len(matches_df)}")
        print(f"Value rows: {len(value_history_df)}")
        return

    stats_df, matches_df, value_history_df = ETL_get_player_stats(
        max_pages=args.max_player_pages,
        max_players_detail=args.max_players,
        headless=not args.headed,
        persist=not args.dry_run,
        player_slug=args.player_slug,
        start_from_slug=args.start_from_slug,
        start_from_href=args.start_from_href,
        start_from_rank=args.start_from_rank,
        resume_checkpoint=args.resume_checkpoint,
        retry_top_players=args.retry_top_players,
        checkpoint_dir=args.checkpoint_dir,
        checkpoint_enabled=not args.no_checkpoint,
        upload_batch_size=args.upload_batch_size,
        pacing_profile=args.pacing_profile,
        circuit_breaker_consecutive_failures=args.circuit_breaker_consecutive_failures,
        circuit_breaker_window_size=args.circuit_breaker_window_size,
        circuit_breaker_window_failures=args.circuit_breaker_window_failures,
        debug_log=args.debug_log,
        run_retention_days=args.run_retention_days,
        terminal_ui=args.terminal_ui,
    )
    if args.dry_run:
        checkpoint_dir = getattr(ETL_get_player_stats, "last_checkpoint_dir", None)
        _print_dry_run_summary(
            stats_df,
            matches_df,
            value_history_df,
            checkpoint_dir=checkpoint_dir,
            terminal_ui=args.terminal_ui,
            max_rows=args.max_players,
        )


if __name__ == "__main__":
    main()
