import pytest
import os
from supabase_client.connection import get_supabase_client

# =============================================================================
# 🧪 UNIT TESTS — test file loading and error handling logic
# These do not use real secrets or connect to Supabase
# =============================================================================

def test_missing_file_raises_file_not_found():
    """
    If the secrets file does not exist, the function should raise FileNotFoundError.
    """
    with pytest.raises(FileNotFoundError):
        get_supabase_client(secrets_path_override="/nonexistent_path/supabase.toml")


def test_missing_keys_raise_keyerror(tmp_path):
    """
    If the secrets file is missing either 'url' or 'anon_key',
    the function should raise a KeyError.
    """
    # Create a fake supabase.toml missing the 'anon_key'
    secrets_path = tmp_path / "supabase.toml"
    secrets_path.write_text("""
        [supabase]
        url = "https://valid-url.supabase.co"
        """)

    with pytest.raises(KeyError):
        get_supabase_client(secrets_path_override=str(secrets_path))


def test_valid_secrets_structure(tmp_path):
    """
    Confirms that a valid toml file with correct keys does not raise any errors.
    """
    secrets_path = tmp_path / "supabase.toml"
    secrets_path.write_text("""
        [supabase]
        url = "https://valid-url.supabase.co"
        anon_key = "test-key-123"
        """)

    client = get_supabase_client(secrets_path_override=str(secrets_path))
    assert client is not None


# =============================================================================
# 🔌 FUNCTIONAL TEST — only runs if real secrets file exists
# These tests DO attempt a real connection to Supabase
# They should be skipped in CI unless you explicitly manage secrets
# =============================================================================
# def test_real_connection_if_secrets_exist():
#     """
#     Try to connect to Supabase using actual secrets (if they exist locally).
#     This is a lightweight functional test to verify connectivity.
#     """
#     secrets_path = os.path.join("secrets", "supabase.toml")
#     if not os.path.exists(secrets_path):
#         pytest.skip("Skipping real connection test — no secrets/supabase.toml file")
#
#     client = get_supabase_client()
#     response = client.table("articles").select("*").limit(1).execute()
#
#     assert isinstance(response.data, list)  # Expecting a list of rows or empty list
