import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".claude" / "hooks" / "lib"))

from secrets_guard import is_blocked  # noqa: E402


def test_blocks_real_biwenger_secret_file_path():
    payload = {"tool_input": {"file_path": "secrets/biwenger.toml"}}
    assert is_blocked(payload) is not None


def test_blocks_relative_dot_slash_secret_file_path():
    payload = {"tool_input": {"file_path": "./secrets/supabase.toml"}}
    assert is_blocked(payload) is not None


def test_blocks_cat_command_on_real_secret():
    payload = {"tool_input": {"command": "cat secrets/biwenger.toml"}}
    assert is_blocked(payload) is not None


def test_blocks_ripgrep_command_over_secrets_dir():
    payload = {"tool_input": {"command": "rg anon_key secrets/"}}
    assert is_blocked(payload) is not None


def test_allows_biwenger_example_template():
    payload = {"tool_input": {"file_path": "secrets/biwenger.example.toml"}}
    assert is_blocked(payload) is None


def test_allows_supabase_example_template():
    payload = {"tool_input": {"file_path": "secrets/supabase.example.toml"}}
    assert is_blocked(payload) is None


def test_allows_sed_command_on_example_template():
    payload = {"tool_input": {"command": "sed -n '1,80p' secrets/biwenger.example.toml"}}
    assert is_blocked(payload) is None


def test_allows_unrelated_docs_file():
    payload = {"tool_input": {"file_path": "docs/repo_architecture_audit.md"}}
    assert is_blocked(payload) is None
