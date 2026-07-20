import tomllib as toml
from pathlib import Path

DEFAULT_ROOT_URL = "https://biwenger.as.com/"
DEFAULT_APP_URL = "https://biwenger.as.com/app"


def load_biwenger_credentials(profile: str = "biwenger") -> dict:
    """
    Load Biwenger credentials from secrets/biwenger.toml.

    Args:
        profile: Which section to read. Usually:
                 - "biwenger" (your main account)
                 - "biwenger_player_scraper" (secondary account)

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
