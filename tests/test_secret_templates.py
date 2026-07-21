import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_biwenger_secret_template_has_required_profiles():
    template = ROOT / "secrets" / "biwenger.example.toml"
    template_text = template.read_text()
    config = tomllib.loads(template_text)

    for profile in ("biwenger", "biwenger_player_scraper"):
        assert profile in config
        assert config[profile]["biwenger_email"]
        assert config[profile]["biwenger_password"]

    assert "Personal/current-team account only" in template_text
    assert "Dedicated scraper/test account" in template_text


def test_supabase_secret_template_has_required_fields():
    template = ROOT / "secrets" / "supabase.example.toml"
    config = tomllib.loads(template.read_text())

    assert config["supabase"]["url"]
    assert config["supabase"]["anon_key"]
