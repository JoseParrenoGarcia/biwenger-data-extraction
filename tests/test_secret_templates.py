import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_biwenger_secret_template_has_required_profiles():
    template = ROOT / "secrets" / "biwenger.example.toml"
    config = tomllib.loads(template.read_text())

    for profile in ("biwenger", "biwenger_player_scraper"):
        assert profile in config
        assert config[profile]["biwenger_email"]
        assert config[profile]["biwenger_password"]


def test_supabase_secret_template_has_required_fields():
    template = ROOT / "secrets" / "supabase.example.toml"
    config = tomllib.loads(template.read_text())

    assert config["supabase"]["url"]
    assert config["supabase"]["anon_key"]
