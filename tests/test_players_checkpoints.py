import json
import logging
import os
from datetime import datetime, timedelta, timezone

import pandas as pd

from scraping_biwenger.players.checkpoints import (
    PlayerRunCheckpoint,
    cleanup_old_player_runs,
    read_checkpoint_successful_slugs,
    read_latest_failed_players,
    read_player_checkpoint,
    read_selected_players,
)
from scraping_biwenger.players.pipeline import _concat_frames, run_player_pipeline, upload_player_checkpoint
from scraping_biwenger.players.transform import (
    PLAYER_MATCHES_COLUMNS,
    PLAYER_STATS_COLUMNS,
    PLAYER_VALUE_COLUMNS,
)
from scraping_biwenger.shared.timing import log_timing_debug


def test_player_checkpoint_writes_metadata_and_payloads(tmp_path):
    checkpoint = PlayerRunCheckpoint(
        root_dir=tmp_path,
        run_id="test-run",
        metadata={"pipeline": "get_player_stats", "persist_requested": False},
    )

    stats_df = pd.DataFrame(
        [
            {
                "player_name": "Player One",
                "team": "Athletic",
                "slug": "player-one",
                "scoring_system": "sofascore",
                "as_of_date": "2026-07-20",
            }
        ],
        columns=PLAYER_STATS_COLUMNS,
    )
    matches_df = pd.DataFrame(columns=PLAYER_MATCHES_COLUMNS)
    value_df = pd.DataFrame(
        [
            {
                "slug": "player-one",
                "player_name": "Player One",
                "team": "Athletic",
                "date": "2026-07-20",
                "market_value_eur": 1000000,
            }
        ],
        columns=PLAYER_VALUE_COLUMNS,
    )

    counts = checkpoint.append_payload(
        player={"name": "Player One", "slug": "player-one"},
        stats_df=stats_df,
        matches_df=matches_df,
        value_history_df=value_df,
    )
    checkpoint.append_player_error(
        player={"name": "Player One", "slug": "player-one"},
        stage="scrape_matches",
        message="No rows",
    )
    checkpoint.append_upload_error(
        batch_number=1,
        stats_rows=1,
        match_rows=0,
        value_rows=1,
        message="Supabase unavailable",
    )
    checkpoint.write_selected_players(
        [{"rank": 1, "name": "Player One", "slug": "player-one", "href": "/la-liga/players/player-one"}]
    )
    checkpoint.update_metadata({"selected_player_count": 1, "selected_manifest_written": True})

    assert counts == {"stats": 1, "matches": 0, "values": 1}
    metadata = json.loads((checkpoint.run_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["run_id"] == "test-run"
    assert metadata["pipeline"] == "get_player_stats"
    assert metadata["selected_player_count"] == 1
    assert (checkpoint.run_dir / "player_stats.jsonl").read_text(encoding="utf-8").count("\n") == 1
    assert (checkpoint.run_dir / "player_values.jsonl").read_text(encoding="utf-8").count("\n") == 1
    assert (checkpoint.run_dir / "selected_players.jsonl").read_text(encoding="utf-8").count("\n") == 1
    assert (checkpoint.run_dir / "errors.jsonl").read_text(encoding="utf-8").count("\n") == 1
    assert (checkpoint.run_dir / "upload_errors.jsonl").read_text(encoding="utf-8").count("\n") == 1


def test_read_player_checkpoint_reconstructs_payload_shapes(tmp_path):
    checkpoint = PlayerRunCheckpoint(root_dir=tmp_path, run_id="test-run", metadata={})
    checkpoint.append_payload(
        player={"name": "Player One", "slug": "player-one"},
        stats_df=pd.DataFrame(
            [{"player_name": "Player One", "team": "Athletic", "slug": "player-one"}],
            columns=["player_name", "team", "slug"],
        ),
        matches_df=pd.DataFrame(
            [{"player_name": "Player One", "team": "Athletic", "slug": "player-one"}],
            columns=["player_name", "team", "slug"],
        ),
        value_history_df=pd.DataFrame(
            [{"slug": "player-one", "player_name": "Player One", "team": "Athletic"}],
            columns=["slug", "player_name", "team"],
        ),
    )

    payload = read_player_checkpoint(checkpoint.run_dir)

    assert list(payload.stats_df.columns) == PLAYER_STATS_COLUMNS
    assert list(payload.matches_df.columns) == PLAYER_MATCHES_COLUMNS
    assert list(payload.value_history_df.columns) == PLAYER_VALUE_COLUMNS
    assert payload.stats_df.loc[0, "slug"] == "player-one"


def test_read_empty_player_checkpoint_returns_empty_payload_shapes(tmp_path):
    checkpoint = PlayerRunCheckpoint(root_dir=tmp_path, run_id="empty-run", metadata={})

    payload = read_player_checkpoint(checkpoint.run_dir)

    assert list(payload.stats_df.columns) == PLAYER_STATS_COLUMNS
    assert list(payload.matches_df.columns) == PLAYER_MATCHES_COLUMNS
    assert list(payload.value_history_df.columns) == PLAYER_VALUE_COLUMNS
    assert payload.stats_df.empty
    assert payload.matches_df.empty
    assert payload.value_history_df.empty


def test_selected_players_round_trip(tmp_path):
    checkpoint = PlayerRunCheckpoint(root_dir=tmp_path, run_id="manifest-run", metadata={})
    checkpoint.write_selected_players(
        [
            {
                "rank": 1,
                "name": "Player One",
                "slug": "player-one",
                "href": "/la-liga/players/player-one",
                "attempt": "initial",
                "open_by_href_only": False,
            }
        ]
    )

    selected = read_selected_players(checkpoint.run_dir)

    assert selected == [
        {
            "rank": 1,
            "name": "Player One",
            "slug": "player-one",
            "href": "/la-liga/players/player-one",
            "attempt": "initial",
            "open_by_href_only": False,
        }
    ]


def test_checkpoint_successful_slugs_and_latest_failures(tmp_path):
    checkpoint = PlayerRunCheckpoint(root_dir=tmp_path, run_id="resume-run", metadata={})
    checkpoint.append_payload(
        player={"name": "Player One", "slug": "player-one"},
        stats_df=pd.DataFrame([{"slug": "player-one"}], columns=["slug"]),
        matches_df=pd.DataFrame(columns=PLAYER_MATCHES_COLUMNS),
        value_history_df=pd.DataFrame(columns=PLAYER_VALUE_COLUMNS),
    )
    checkpoint.append_player_error(
        player={"name": "Player Two", "slug": "player-two"},
        stage="open_player",
        message="failed once",
    )
    checkpoint.append_player_error(
        player={"name": "Player Two", "slug": "player-two"},
        stage="scrape_detail",
        message="failed twice",
    )

    assert read_checkpoint_successful_slugs(checkpoint.run_dir) == {"player-one"}
    latest_failures = read_latest_failed_players(checkpoint.run_dir)
    assert latest_failures["player-two"]["stage"] == "scrape_detail"


def test_upload_player_checkpoint_uses_existing_persistence_path(tmp_path, monkeypatch):
    checkpoint = PlayerRunCheckpoint(root_dir=tmp_path, run_id="upload-run", metadata={})
    checkpoint.append_payload(
        player={"name": "Player One", "slug": "player-one"},
        stats_df=pd.DataFrame(
            [{"player_name": "Player One", "team": "Athletic", "slug": "player-one"}],
            columns=["player_name", "team", "slug"],
        ),
        matches_df=pd.DataFrame(columns=PLAYER_MATCHES_COLUMNS),
        value_history_df=pd.DataFrame(columns=PLAYER_VALUE_COLUMNS),
    )
    calls = []

    def fake_persist(stats_df, matches_df, value_history_df, *, logger=None, supabase=None):
        calls.append((stats_df, matches_df, value_history_df, supabase))

    monkeypatch.setattr("scraping_biwenger.players.pipeline.persist_player_outputs", fake_persist)

    stats_df, matches_df, value_df = upload_player_checkpoint(
        str(checkpoint.run_dir),
        logger=None,
        supabase=object(),
    )

    assert len(calls) == 1
    assert len(stats_df) == 1
    assert matches_df.empty
    assert value_df.empty


def test_upload_player_checkpoint_writes_upload_log_inside_run_dir(tmp_path, monkeypatch):
    checkpoint = PlayerRunCheckpoint(root_dir=tmp_path, run_id="upload-log-run", metadata={})
    calls = []

    def fake_persist(stats_df, matches_df, value_history_df, *, logger=None, supabase=None):
        calls.append(logger)

    monkeypatch.setattr("scraping_biwenger.players.pipeline.persist_player_outputs", fake_persist)

    upload_player_checkpoint(str(checkpoint.run_dir))

    upload_log = checkpoint.run_dir / "upload.log"
    assert len(calls) == 1
    assert upload_log.exists()
    assert "Uploading player checkpoint from" in upload_log.read_text(encoding="utf-8")


def test_concat_frames_returns_expected_empty_shape():
    df = _concat_frames([], PLAYER_STATS_COLUMNS)

    assert list(df.columns) == PLAYER_STATS_COLUMNS
    assert df.empty


def test_run_player_pipeline_replays_checkpoint_after_batch_upload_failure(tmp_path, monkeypatch):
    calls = []

    class FakeBrowser:
        def close(self):
            pass

    class FakeContext:
        def close(self):
            pass

    class FakePlaywright:
        def stop(self):
            pass

    class FakeLogger:
        def info(self, *args, **kwargs):
            pass

        def debug(self, *args, **kwargs):
            pass

        def warning(self, *args, **kwargs):
            pass

        def exception(self, *args, **kwargs):
            pass

    def fake_start_browser_accept_cookies(*, headless, logger):
        return FakePlaywright(), FakeBrowser(), FakeContext(), object()

    def fake_scrape_players_snapshot(page, logger, **kwargs):
        on_player_payload = kwargs["on_player_payload"]
        on_player_payload(
            player={"name": "Player One", "slug": "player-one"},
            detail_rows=[
                {
                    "player_name": "Player One",
                    "team": "Athletic",
                    "slug": "player-one",
                    "scoring_system": "sofascore",
                }
            ],
            match_rows=[],
            value_history_rows=[],
            processed_count=1,
        )
        return (
            pd.DataFrame(
                [
                    {
                        "player_name": "Player One",
                        "team": "Athletic",
                        "slug": "player-one",
                    }
                ],
                columns=PLAYER_STATS_COLUMNS,
            ),
            pd.DataFrame(columns=PLAYER_MATCHES_COLUMNS),
            pd.DataFrame(columns=PLAYER_VALUE_COLUMNS),
        )

    def fake_persist(stats_df, matches_df, value_history_df, *, logger=None, supabase=None):
        calls.append(len(stats_df))
        if len(calls) == 1:
            raise RuntimeError("Supabase temporarily unavailable")

    monkeypatch.setattr(
        "scraping_biwenger.players.pipeline.load_biwenger_credentials", lambda profile: {"email": "x", "password": "y"}
    )
    monkeypatch.setattr(
        "scraping_biwenger.players.pipeline.start_browser_accept_cookies", fake_start_browser_accept_cookies
    )
    monkeypatch.setattr("scraping_biwenger.players.pipeline.perform_login", lambda page, email, password, logger: None)
    monkeypatch.setattr("scraping_biwenger.players.pipeline.scrape_players_snapshot", fake_scrape_players_snapshot)
    monkeypatch.setattr("scraping_biwenger.players.pipeline.persist_player_outputs", fake_persist)

    run_player_pipeline(
        headless=True,
        persist=True,
        max_pages=1,
        max_players_detail=1,
        checkpoint_dir=str(tmp_path),
        upload_batch_size=1,
        logger=FakeLogger(),
    )

    assert calls == [1, 1]
    run_dir = next(tmp_path.iterdir())
    assert (run_dir / "upload_errors.jsonl").read_text(encoding="utf-8").count("\n") == 1


def test_cleanup_old_player_runs_deletes_only_expired_directories(tmp_path):
    old_run = tmp_path / "old-run"
    recent_run = tmp_path / "recent-run"
    loose_file = tmp_path / "not-a-run.txt"
    old_run.mkdir()
    recent_run.mkdir()
    loose_file.write_text("keep me", encoding="utf-8")

    now = datetime(2026, 7, 20, tzinfo=timezone.utc)
    old_mtime = (now - timedelta(days=8)).timestamp()
    recent_mtime = (now - timedelta(days=2)).timestamp()
    os.utime(old_run, (old_mtime, old_mtime))
    os.utime(recent_run, (recent_mtime, recent_mtime))

    deleted = cleanup_old_player_runs(tmp_path, retention_days=7, now=now)

    assert [path.name for path in deleted] == ["old-run"]
    assert not old_run.exists()
    assert recent_run.exists()
    assert loose_file.exists()


def test_timing_records_are_debug_only(caplog):
    logger = logging.getLogger("test-player-timing")
    logger.handlers = []
    logger.propagate = True
    logger.setLevel(logging.DEBUG)

    with caplog.at_level(logging.INFO, logger="test-player-timing"):
        log_timing_debug(logger, "Player statistics points parse", 0, player_slug="kita")
    assert "TIMING" not in caplog.text

    caplog.clear()
    with caplog.at_level(logging.DEBUG, logger="test-player-timing"):
        log_timing_debug(logger, "Player statistics points parse", 0, player_slug="kita")
    assert "TIMING stage=player_statistics_points_parse player_slug=kita" in caplog.text


def test_run_player_pipeline_writes_log_inside_checkpoint_run_dir(tmp_path, monkeypatch):
    class FakeBrowser:
        def close(self):
            pass

    class FakeContext:
        def close(self):
            pass

    class FakePlaywright:
        def stop(self):
            pass

    def fake_start_browser_accept_cookies(*, headless, logger):
        return FakePlaywright(), FakeBrowser(), FakeContext(), object()

    def fake_scrape_players_snapshot(page, logger, **kwargs):
        return (
            pd.DataFrame(columns=PLAYER_STATS_COLUMNS),
            pd.DataFrame(columns=PLAYER_MATCHES_COLUMNS),
            pd.DataFrame(columns=PLAYER_VALUE_COLUMNS),
        )

    monkeypatch.setattr(
        "scraping_biwenger.players.pipeline.load_biwenger_credentials", lambda profile: {"email": "x", "password": "y"}
    )
    monkeypatch.setattr(
        "scraping_biwenger.players.pipeline.start_browser_accept_cookies", fake_start_browser_accept_cookies
    )
    monkeypatch.setattr("scraping_biwenger.players.pipeline.perform_login", lambda page, email, password, logger: None)
    monkeypatch.setattr("scraping_biwenger.players.pipeline.scrape_players_snapshot", fake_scrape_players_snapshot)

    run_player_pipeline(
        headless=True,
        persist=False,
        max_pages=1,
        max_players_detail=1,
        checkpoint_dir=str(tmp_path),
    )

    run_dir = next(path for path in tmp_path.iterdir() if path.is_dir())
    run_log = run_dir / "run.log"
    assert run_log.exists()
    assert "Starting ETL: get_player_stats" in run_log.read_text(encoding="utf-8")


def test_run_player_pipeline_does_not_build_terminal_ui_by_default(tmp_path, monkeypatch):
    calls = {"ui_init": 0}

    class FakeBrowser:
        def close(self):
            pass

    class FakeContext:
        def close(self):
            pass

    class FakePlaywright:
        def stop(self):
            pass

    class FakeLogger:
        def info(self, *args, **kwargs):
            pass

        def debug(self, *args, **kwargs):
            pass

        def warning(self, *args, **kwargs):
            pass

        def exception(self, *args, **kwargs):
            pass

    def fake_start_browser_accept_cookies(*, headless, logger):
        return FakePlaywright(), FakeBrowser(), FakeContext(), object()

    def fake_scrape_players_snapshot(page, logger, **kwargs):
        return (
            pd.DataFrame(columns=PLAYER_STATS_COLUMNS),
            pd.DataFrame(columns=PLAYER_MATCHES_COLUMNS),
            pd.DataFrame(columns=PLAYER_VALUE_COLUMNS),
        )

    class FakeUI:
        def __init__(self):
            calls["ui_init"] += 1

        def handle_event(self, event):
            return None

        def close(self):
            return None

    monkeypatch.setattr(
        "scraping_biwenger.players.pipeline.load_biwenger_credentials", lambda profile: {"email": "x", "password": "y"}
    )
    monkeypatch.setattr(
        "scraping_biwenger.players.pipeline.start_browser_accept_cookies", fake_start_browser_accept_cookies
    )
    monkeypatch.setattr("scraping_biwenger.players.pipeline.perform_login", lambda page, email, password, logger: None)
    monkeypatch.setattr("scraping_biwenger.players.pipeline.scrape_players_snapshot", fake_scrape_players_snapshot)
    monkeypatch.setattr("scraping_biwenger.players.pipeline.PlayerRunTerminalUI", FakeUI)

    run_player_pipeline(
        headless=True,
        persist=False,
        max_pages=1,
        max_players_detail=1,
        checkpoint_dir=str(tmp_path),
        logger=FakeLogger(),
    )

    assert calls["ui_init"] == 0


def test_run_player_pipeline_emits_batch_upload_events(tmp_path, monkeypatch):
    events = []

    class FakeBrowser:
        def close(self):
            pass

    class FakeContext:
        def close(self):
            pass

    class FakePlaywright:
        def stop(self):
            pass

    class FakeLogger:
        def info(self, *args, **kwargs):
            pass

        def debug(self, *args, **kwargs):
            pass

        def warning(self, *args, **kwargs):
            pass

        def exception(self, *args, **kwargs):
            pass

    def fake_start_browser_accept_cookies(*, headless, logger):
        return FakePlaywright(), FakeBrowser(), FakeContext(), object()

    def fake_scrape_players_snapshot(page, logger, **kwargs):
        on_player_payload = kwargs["on_player_payload"]
        on_player_payload(
            player={"name": "Player One", "slug": "player-one"},
            detail_rows=[
                {
                    "player_name": "Player One",
                    "team": "Athletic",
                    "slug": "player-one",
                    "scoring_system": "sofascore",
                }
            ],
            match_rows=[],
            value_history_rows=[],
            processed_count=1,
        )
        return (
            pd.DataFrame(
                [{"player_name": "Player One", "team": "Athletic", "slug": "player-one"}],
                columns=PLAYER_STATS_COLUMNS,
            ),
            pd.DataFrame(columns=PLAYER_MATCHES_COLUMNS),
            pd.DataFrame(columns=PLAYER_VALUE_COLUMNS),
        )

    class FakeUI:
        def handle_event(self, event):
            events.append(event)

        def close(self):
            return None

    monkeypatch.setattr(
        "scraping_biwenger.players.pipeline.load_biwenger_credentials", lambda profile: {"email": "x", "password": "y"}
    )
    monkeypatch.setattr(
        "scraping_biwenger.players.pipeline.start_browser_accept_cookies", fake_start_browser_accept_cookies
    )
    monkeypatch.setattr("scraping_biwenger.players.pipeline.perform_login", lambda page, email, password, logger: None)
    monkeypatch.setattr("scraping_biwenger.players.pipeline.scrape_players_snapshot", fake_scrape_players_snapshot)
    monkeypatch.setattr("scraping_biwenger.players.pipeline.persist_player_outputs", lambda *args, **kwargs: None)
    monkeypatch.setattr("scraping_biwenger.players.pipeline.PlayerRunTerminalUI", lambda: FakeUI())

    run_player_pipeline(
        headless=True,
        persist=True,
        max_pages=1,
        max_players_detail=1,
        checkpoint_dir=str(tmp_path),
        upload_batch_size=1,
        terminal_ui=True,
        logger=FakeLogger(),
    )

    event_types = [event["type"] for event in events]
    assert "run_started" in event_types
    assert "checkpoint_written" in event_types
    assert "batch_upload_started" in event_types
    assert "batch_upload_finished" in event_types
    assert "run_finished" in event_types


def test_run_player_pipeline_writes_selected_player_manifest(tmp_path, monkeypatch):
    class FakeBrowser:
        def close(self):
            pass

    class FakeContext:
        def close(self):
            pass

    class FakePlaywright:
        def stop(self):
            pass

    class FakeLogger:
        def info(self, *args, **kwargs):
            pass

        def debug(self, *args, **kwargs):
            pass

        def warning(self, *args, **kwargs):
            pass

        def exception(self, *args, **kwargs):
            pass

    def fake_start_browser_accept_cookies(*, headless, logger):
        return FakePlaywright(), FakeBrowser(), FakeContext(), object()

    def fake_scrape_players_snapshot(page, logger, **kwargs):
        kwargs["on_players_selected"](
            [
                {
                    "rank": 1,
                    "name": "Player One",
                    "slug": "player-one",
                    "href": "/la-liga/players/player-one",
                    "attempt": "initial",
                    "open_by_href_only": False,
                }
            ]
        )
        return (
            pd.DataFrame(columns=PLAYER_STATS_COLUMNS),
            pd.DataFrame(columns=PLAYER_MATCHES_COLUMNS),
            pd.DataFrame(columns=PLAYER_VALUE_COLUMNS),
        )

    monkeypatch.setattr(
        "scraping_biwenger.players.pipeline.load_biwenger_credentials", lambda profile: {"email": "x", "password": "y"}
    )
    monkeypatch.setattr(
        "scraping_biwenger.players.pipeline.start_browser_accept_cookies", fake_start_browser_accept_cookies
    )
    monkeypatch.setattr("scraping_biwenger.players.pipeline.perform_login", lambda page, email, password, logger: None)
    monkeypatch.setattr("scraping_biwenger.players.pipeline.scrape_players_snapshot", fake_scrape_players_snapshot)

    run_player_pipeline(
        headless=True,
        persist=False,
        max_pages=1,
        max_players_detail=1,
        checkpoint_dir=str(tmp_path),
        logger=FakeLogger(),
    )

    run_dir = next(path for path in tmp_path.iterdir() if path.is_dir())
    selected_players = read_selected_players(run_dir)
    metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))

    assert len(selected_players) == 1
    assert selected_players[0]["slug"] == "player-one"
    assert metadata["selected_player_count"] == 1
    assert metadata["selected_manifest_written"] is True
