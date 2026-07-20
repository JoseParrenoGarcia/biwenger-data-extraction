import json

import pandas as pd

from scraping_biwenger.players.checkpoints import (
    PlayerRunCheckpoint,
    read_player_checkpoint,
)
from scraping_biwenger.players.pipeline import _concat_frames, upload_player_checkpoint
from scraping_biwenger.players.pipeline import run_player_pipeline
from scraping_biwenger.players.transform import (
    PLAYER_MATCHES_COLUMNS,
    PLAYER_STATS_COLUMNS,
    PLAYER_VALUE_COLUMNS,
)


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

    assert counts == {"stats": 1, "matches": 0, "values": 1}
    metadata = json.loads((checkpoint.run_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["run_id"] == "test-run"
    assert metadata["pipeline"] == "get_player_stats"
    assert (checkpoint.run_dir / "player_stats.jsonl").read_text(encoding="utf-8").count("\n") == 1
    assert (checkpoint.run_dir / "player_values.jsonl").read_text(encoding="utf-8").count("\n") == 1
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

    monkeypatch.setattr("scraping_biwenger.players.pipeline.load_biwenger_credentials", lambda profile: {"email": "x", "password": "y"})
    monkeypatch.setattr("scraping_biwenger.players.pipeline.start_browser_accept_cookies", fake_start_browser_accept_cookies)
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
