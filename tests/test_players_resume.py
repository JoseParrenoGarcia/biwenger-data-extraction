import pandas as pd
import pytest

from scraping_biwenger.players.checkpoints import PlayerRunCheckpoint
from scraping_biwenger.players.pipeline import _build_resume_players
from scraping_biwenger.players.scrape import _filter_selected_players
from scraping_biwenger.players.transform import PLAYER_MATCHES_COLUMNS, PLAYER_VALUE_COLUMNS


def _write_resume_fixture(tmp_path):
    checkpoint = PlayerRunCheckpoint(root_dir=tmp_path, run_id="resume-source", metadata={})
    checkpoint.write_selected_players(
        [
            {"rank": 1, "name": "One", "slug": "one", "href": "/la-liga/players/one", "attempt": "initial"},
            {"rank": 2, "name": "Two", "slug": "two", "href": "/la-liga/players/two", "attempt": "initial"},
            {"rank": 3, "name": "Three", "slug": "three", "href": "/la-liga/players/three", "attempt": "initial"},
            {"rank": 4, "name": "Four", "slug": "four", "href": "/la-liga/players/four", "attempt": "initial"},
        ]
    )
    checkpoint.append_payload(
        player={"name": "One", "slug": "one"},
        stats_df=pd.DataFrame([{"slug": "one"}], columns=["slug"]),
        matches_df=pd.DataFrame(columns=PLAYER_MATCHES_COLUMNS),
        value_history_df=pd.DataFrame(columns=PLAYER_VALUE_COLUMNS),
    )
    checkpoint.append_player_error(
        player={"name": "Two", "slug": "two", "href": "/la-liga/players/two", "rank": 2, "attempt": "initial"},
        stage="open_player",
        message="failed",
    )
    return checkpoint.run_dir


def test_filter_selected_players_by_slug_href_and_rank():
    selected_players = [
        {"rank": 1, "slug": "one", "href": "/la-liga/players/one"},
        {"rank": 2, "slug": "two", "href": "/la-liga/players/two"},
        {"rank": 3, "slug": "three", "href": "/la-liga/players/three"},
    ]

    assert [p["slug"] for p in _filter_selected_players(selected_players, start_from_slug="two")] == ["two", "three"]
    assert [p["slug"] for p in _filter_selected_players(selected_players, start_from_href="/la-liga/players/two")] == [
        "two",
        "three",
    ]
    assert [p["slug"] for p in _filter_selected_players(selected_players, start_from_rank=2)] == ["two", "three"]


def test_filter_selected_players_raises_on_missing_target():
    with pytest.raises(ValueError, match="Could not find start-from slug"):
        _filter_selected_players([{"rank": 1, "slug": "one", "href": "/la-liga/players/one"}], start_from_slug="two")


def test_build_resume_players_skips_successes_and_prioritizes_failures(tmp_path):
    run_dir = _write_resume_fixture(tmp_path)

    players, failed_count, tail_count = _build_resume_players(run_dir=str(run_dir))

    assert [player["slug"] for player in players] == ["two", "three", "four"]
    assert players[0]["attempt"] == "resume_retry"
    assert players[0]["open_by_href_only"] is True
    assert players[1]["attempt"] == "resume_tail"
    assert failed_count == 1
    assert tail_count == 2


def test_build_resume_players_applies_manual_start_filter(tmp_path):
    run_dir = _write_resume_fixture(tmp_path)

    players, _, _ = _build_resume_players(run_dir=str(run_dir), start_from_slug="three")

    assert [player["slug"] for player in players] == ["three", "four"]


def test_build_resume_players_requires_manifest_for_automatic_resume(tmp_path):
    checkpoint = PlayerRunCheckpoint(root_dir=tmp_path, run_id="old-run", metadata={})
    checkpoint.selected_players_path.unlink()

    with pytest.raises(ValueError, match="Automatic resume requires selected_players.jsonl"):
        _build_resume_players(run_dir=str(checkpoint.run_dir))


def test_build_resume_players_rejects_old_manifestless_runs_even_with_manual_filter(tmp_path):
    checkpoint = PlayerRunCheckpoint(root_dir=tmp_path, run_id="old-run-manual", metadata={})
    checkpoint.selected_players_path.unlink()

    with pytest.raises(ValueError, match="must be resumed manually from an explicit start point"):
        _build_resume_players(run_dir=str(checkpoint.run_dir), start_from_slug="two")
