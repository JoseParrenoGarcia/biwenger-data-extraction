from scraping_biwenger.players.run_events import build_event_emitter, make_player_run_event
from scraping_biwenger.players.terminal_ui import PlayerRunTerminalState


def test_event_emitter_notifies_subscribers():
    events = []
    emitter = build_event_emitter(events.append)

    emitter.emit("run_started", run_id="run-1", run_dir="run_artifacts/player_runs/run-1")

    assert len(events) == 1
    assert events[0]["type"] == "run_started"
    assert events[0]["run_id"] == "run-1"
    assert "recorded_at" in events[0]


def test_terminal_ui_state_tracks_progress_and_uploads():
    state = PlayerRunTerminalState()

    state.apply_event(
        make_player_run_event(
            "run_started",
            run_id="run-1",
            run_dir="run_artifacts/player_runs/run-1",
            dry_run=True,
            headed=True,
            max_players_detail=2,
            retry_top_players=0,
            upload_batch_size=10,
        )
    )
    state.apply_event(
        make_player_run_event(
            "player_started",
            player_name="Kita",
            player_slug="kazunari-kita",
            rank=1,
            total_players=2,
            attempt_label="initial",
            team="Getafe",
        )
    )
    state.apply_event(
        make_player_run_event(
            "checkpoint_written",
            player_name="Kita",
            player_slug="kazunari-kita",
            stats_rows=1,
            match_rows=0,
            value_rows=17,
            processed_count=1,
        )
    )
    state.apply_event(
        make_player_run_event(
            "player_finished",
            player_name="Kita",
            player_slug="kazunari-kita",
            processed_count=1,
            total_players=2,
            scoring_system="SofaScore",
            stats_rows=1,
            match_rows=0,
            value_rows=17,
            stage="ok",
            note="no_match_history",
        )
    )
    state.apply_event(
        make_player_run_event(
            "batch_upload_started",
            batch_number=1,
            stats_rows=1,
            match_rows=0,
            value_rows=17,
        )
    )
    state.apply_event(
        make_player_run_event(
            "batch_upload_finished",
            batch_number=1,
            stats_rows=1,
            match_rows=0,
            value_rows=17,
        )
    )

    assert state.run_id == "run-1"
    assert state.processed_players == 1
    assert state.total_players == 2
    assert state.pending_stats_rows == 0
    assert state.pending_match_rows == 0
    assert state.pending_value_rows == 0
    assert state.recent_outcomes[-1].label == "kazunari-kita"
    assert state.recent_outcomes[-1].note == "no_match_history"
    assert state.batch_number == 1


def test_terminal_ui_state_tracks_retry_and_failure():
    state = PlayerRunTerminalState()

    state.apply_event(
        make_player_run_event(
            "retry_queued",
            player_name="Marc Roca",
            player_slug="marc-roca",
            rank=15,
            stage="select_scoring_system",
        )
    )
    state.apply_event(make_player_run_event("retry_pass_started", retry_count=1, retry_top_players=150))
    state.apply_event(
        make_player_run_event(
            "player_failed",
            player_name="Marc Roca",
            player_slug="marc-roca",
            stage="select_scoring_system",
            message="Points tab did not load usable content",
        )
    )
    state.apply_event(
        make_player_run_event(
            "retry_pass_finished",
            retry_count=1,
            recovered_count=0,
            failed_count=1,
        )
    )

    assert state.retry_queue_count == 1
    assert state.retry_active is False
    assert state.retry_failed == 1
    assert state.warning_count == 1
    assert state.recent_outcomes[-1].status == "failed"


def test_terminal_ui_state_tracks_value_incomplete_and_value_retry():
    state = PlayerRunTerminalState()

    state.apply_event(
        make_player_run_event(
            "player_value_incomplete",
            player_name="Courtois",
            player_slug="t-courtois",
            reason="csv_timeout",
            match_rows=32,
            value_rows=0,
        )
    )
    state.apply_event(
        make_player_run_event(
            "player_finished",
            player_name="Courtois",
            player_slug="t-courtois",
            processed_count=54,
            total_players=510,
            scoring_system="SofaScore",
            stats_rows=1,
            match_rows=32,
            value_rows=0,
            stage="value_incomplete",
        )
    )
    state.apply_event(
        make_player_run_event(
            "player_value_retry_queued",
            player_name="Courtois",
            player_slug="t-courtois",
            rank=54,
            reason="csv_timeout",
        )
    )
    state.apply_event(make_player_run_event("value_retry_pass_started", retry_count=1))
    state.apply_event(
        make_player_run_event("value_retry_pass_finished", retry_count=1, recovered_count=1, failed_count=0)
    )

    assert state.warning_count == 1
    assert state.retry_queue_count == 1
    assert state.retry_active is False
    assert state.retry_recovered == 1
    assert state.recent_outcomes[-1].status == "warning"
