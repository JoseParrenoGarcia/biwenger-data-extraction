import os
from pathlib import Path
import tomllib as toml

def load_biwenger_credentials() -> dict:
    """
    Load Biwenger credentials from secrets/biwenger.toml.

    Returns:
        dict: {"email": str, "password": str}
    """
    # Resolve repo root relative to this file
    current_dir = Path(__file__).resolve().parent
    root_dir = current_dir.parent  # one level up from scraping_biwenger/
    secrets_path = root_dir / "secrets" / "biwenger.toml"

    if not secrets_path.exists():
        raise FileNotFoundError(f"Secrets file not found: {secrets_path}")

    with open(secrets_path, "rb") as f:
        config = toml.load(f)

    email = config.get("biwenger", {}).get("biwenger_email")
    password = config.get("biwenger", {}).get("biwenger_password")

    if not email or not password:
        raise ValueError(f"Missing 'biwenger_email' or 'biwenger_password' in {secrets_path}")

    return {"email": email, "password": password}


if __name__ == "__main__":
    creds = load_biwenger_credentials()
    # print(creds["email"])  # your biwenger email
    # print(creds["password"])  # your biwenger password
