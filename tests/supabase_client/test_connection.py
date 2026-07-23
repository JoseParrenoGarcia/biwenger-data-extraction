import pytest

from supabase_client.connection import (
    get_supabase_admin_client,
    get_supabase_backend_read_client,
    get_supabase_client,
)

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


def test_missing_service_role_key_raises_keyerror(tmp_path):
    """
    If the secrets file is missing the service role key,
    the function should raise a KeyError.
    """
    secrets_path = tmp_path / "supabase.toml"
    secrets_path.write_text("""
        [supabase]
        url = "https://valid-url.supabase.co"
        anon_key = "publishable-placeholder"
        """)

    with pytest.raises(KeyError):
        get_supabase_admin_client(secrets_path_override=str(secrets_path))


def test_valid_admin_secrets_structure(tmp_path):
    """
    Confirms that a valid toml file with correct keys does not raise any errors.
    """
    secrets_path = tmp_path / "supabase.toml"
    secrets_path.write_text("""
        [supabase]
        url = "https://valid-url.supabase.co"
        anon_key = "publishable-placeholder"
        service_role_key = "service-role-test-key"
        """)

    client = get_supabase_admin_client(secrets_path_override=str(secrets_path))
    assert client is not None


def test_valid_backend_read_secrets_structure(tmp_path):
    secrets_path = tmp_path / "supabase.toml"
    secrets_path.write_text("""
        [supabase]
        url = "https://valid-url.supabase.co"
        service_role_key = "service-role-test-key"
        """)

    client = get_supabase_backend_read_client(secrets_path_override=str(secrets_path))
    assert client is not None


def test_legacy_get_supabase_client_uses_backend_read_client(tmp_path):
    secrets_path = tmp_path / "supabase.toml"
    secrets_path.write_text("""
        [supabase]
        url = "https://valid-url.supabase.co"
        service_role_key = "service-role-test-key"
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
#     response = client.table("biwenger_current_team").select("*").limit(1).execute()
#
#     assert isinstance(response.data, list)  # Expecting a list of rows or empty list
