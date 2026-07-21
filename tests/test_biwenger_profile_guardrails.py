import pytest

from scraping_biwenger.current_team import pipeline as current_team_pipeline
from scraping_biwenger.players import pipeline as player_pipeline
from scraping_biwenger.shared.config import (
    CURRENT_TEAM_PROFILE,
    PLAYER_SCRAPER_PROFILE,
    assert_biwenger_profile_allowed,
)


class _NoopLogger:
    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def debug(self, *args, **kwargs):
        pass

    def exception(self, *args, **kwargs):
        pass


def test_player_scraping_rejects_personal_profile():
    with pytest.raises(ValueError, match="Unsafe Biwenger credential profile"):
        assert_biwenger_profile_allowed(
            use_case="player_scraping",
            profile=CURRENT_TEAM_PROFILE,
        )


def test_current_team_rejects_scraper_profile():
    with pytest.raises(ValueError, match="Unsafe Biwenger credential profile"):
        assert_biwenger_profile_allowed(
            use_case="current_team",
            profile=PLAYER_SCRAPER_PROFILE,
        )


def test_player_pipeline_loads_scraper_profile(monkeypatch):
    requested_profiles = []

    def fake_load_credentials(*, profile):
        requested_profiles.append(profile)
        raise RuntimeError("stop before browser")

    monkeypatch.setattr(player_pipeline, "load_biwenger_credentials", fake_load_credentials)

    with pytest.raises(RuntimeError, match="stop before browser"):
        player_pipeline.run_player_pipeline(
            headless=True,
            persist=False,
            checkpoint_enabled=False,
            logger=_NoopLogger(),
        )

    assert requested_profiles == [PLAYER_SCRAPER_PROFILE]


def test_current_team_pipeline_loads_personal_profile(monkeypatch):
    requested_profiles = []

    def fake_load_credentials(*, profile):
        requested_profiles.append(profile)
        raise RuntimeError("stop before browser")

    monkeypatch.setattr(current_team_pipeline, "load_biwenger_credentials", fake_load_credentials)

    with pytest.raises(RuntimeError, match="stop before browser"):
        current_team_pipeline.run_current_team_pipeline(
            headless=True,
            persist=False,
            logger=_NoopLogger(),
        )

    assert requested_profiles == [CURRENT_TEAM_PROFILE]
