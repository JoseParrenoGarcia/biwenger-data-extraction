import io
from contextlib import redirect_stdout

import pandas as pd
import pytest

from scraping_biwenger.get_player_stats import _print_dry_run_summary, main


def test_terminal_ui_dry_run_summary_skips_dataframe_prints():
    stats_df = pd.DataFrame([{"player_name": "Mbappe"}])
    matches_df = pd.DataFrame([{"round_label": "R1"}])
    values_df = pd.DataFrame([{"date": "2026-07-22"}])

    output = io.StringIO()
    with redirect_stdout(output):
        _print_dry_run_summary(
            stats_df,
            matches_df,
            values_df,
            checkpoint_dir="run_artifacts/player_runs/run-1",
            terminal_ui=True,
        )

    rendered = output.getvalue()
    assert "DRY RUN ONLY" in rendered
    assert "Checkpoint directory: run_artifacts/player_runs/run-1" in rendered
    assert "Summary: 1 stats rows, 1 match rows, 1 value rows." in rendered
    assert "Player Stats - Dry Run" not in rendered


def test_standard_dry_run_summary_keeps_dataframe_sections():
    stats_df = pd.DataFrame([{"player_name": "Mbappe"}])
    matches_df = pd.DataFrame(columns=["round_label"])
    values_df = pd.DataFrame(columns=["date"])

    output = io.StringIO()
    with redirect_stdout(output):
        _print_dry_run_summary(
            stats_df,
            matches_df,
            values_df,
            checkpoint_dir=None,
            terminal_ui=False,
            max_rows=5,
        )

    rendered = output.getvalue()
    assert "Player Stats - Dry Run" in rendered
    assert "Player Matches - Dry Run" in rendered
    assert "Player Value History - Dry Run" in rendered


def test_upload_checkpoint_rejects_resume_and_manual_start_options(monkeypatch):
    monkeypatch.setattr(
        "sys.argv",
        [
            "get_player_stats.py",
            "--upload-checkpoint",
            "run_artifacts/player_runs/run-1",
            "--resume-checkpoint",
            "run_artifacts/player_runs/run-2",
        ],
    )

    with pytest.raises(SystemExit, match="--upload-checkpoint cannot be combined"):
        main()
