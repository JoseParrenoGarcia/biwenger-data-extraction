import tomllib as toml
from pathlib import Path

DEFAULT_ROOT_URL = "https://biwenger.as.com/"
DEFAULT_APP_URL = "https://biwenger.as.com/app"
CURRENT_TEAM_PROFILE = "biwenger"
PLAYER_SCRAPER_PROFILE = "biwenger_player_scraper"

_EXPECTED_PROFILE_BY_USE_CASE = {
    "current_team": CURRENT_TEAM_PROFILE,
    "player_scraping": PLAYER_SCRAPER_PROFILE,
}


def assert_biwenger_profile_allowed(*, use_case: str, profile: str) -> None:
    """
    Guard against accidentally using the personal Biwenger account for bulk scraping.
    """
    expected_profile = _EXPECTED_PROFILE_BY_USE_CASE.get(use_case)
    if expected_profile is None:
        allowed = ", ".join(sorted(_EXPECTED_PROFILE_BY_USE_CASE))
        raise ValueError(f"Unknown Biwenger credential use case '{use_case}'. Expected one of: {allowed}")

    if profile != expected_profile:
        raise ValueError(
            f"Unsafe Biwenger credential profile '{profile}' for use case '{use_case}'. "
            f"Use '{expected_profile}' instead."
        )


def load_biwenger_credentials(profile: str = CURRENT_TEAM_PROFILE) -> dict:
    """
    Load Biwenger credentials from secrets/biwenger.toml.

    Args:
        profile: Which section to read. Usually:
                 - "biwenger" (personal/current-team only)
                 - "biwenger_player_scraper" (high-volume player scraper account)

    Returns:
        dict: {"email": str, "password": str}

    Raises:
        FileNotFoundError: secrets file missing
        ValueError: requested profile missing or incomplete
    """
    # Resolve repo root relative to this file
    current_dir = Path(__file__).resolve().parent
    root_dir = current_dir.parent.parent  # shared/ -> scraping_biwenger/ -> repo root
    secrets_path = root_dir / "secrets" / "biwenger.toml"

    if not secrets_path.exists():
        raise FileNotFoundError(f"Secrets file not found: {secrets_path}")

    with open(secrets_path, "rb") as f:
        config = toml.load(f)

    if profile not in config:
        available = ", ".join(config.keys())
        raise ValueError(f"Profile [{profile}] not found in {secrets_path}. Available sections: {available}")

    section = config.get(profile, {})
    email = section.get("biwenger_email")
    password = section.get("biwenger_password")

    if not email or not password:
        raise ValueError(f"Missing 'biwenger_email' or 'biwenger_password' in section [{profile}] of {secrets_path}")

    return {"email": email, "password": password}
