import os

import toml

from supabase import Client, create_client


def _resolve_secrets_path(secrets_path_override: str | None = None) -> str:
    if secrets_path_override:
        return secrets_path_override
    current_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.abspath(os.path.join(current_dir, ".."))
    return os.path.join(root_dir, "secrets", "supabase.toml")


def _load_supabase_config(secrets_path_override: str | None = None) -> dict:
    secrets_path = _resolve_secrets_path(secrets_path_override=secrets_path_override)
    if os.path.exists(secrets_path):
        config = toml.load(secrets_path)
        supabase_config = config.get("supabase", {})
    elif secrets_path_override:
        # An explicit override is used by tests and local tooling; do not
        # silently replace it with Streamlit's process-level secrets.
        raise FileNotFoundError(f"Missing secrets file at: {secrets_path}")
    else:
        supabase_config = _load_streamlit_supabase_config()
        if supabase_config is None:
            raise FileNotFoundError(
                f"Missing secrets file at: {secrets_path}; configure [supabase] in Streamlit secrets"
            )

    if not supabase_config.get("url"):
        raise KeyError("Missing 'url' in Supabase configuration")
    return supabase_config


def _load_streamlit_supabase_config() -> dict | None:
    """Return the ``[supabase]`` Streamlit secrets section when available."""
    try:
        import streamlit as st

        supabase_config = st.secrets.get("supabase")
    except (FileNotFoundError, ImportError):
        return None

    return dict(supabase_config) if supabase_config else None


def _create_supabase_client(key_name: str, *, secrets_path_override: str | None = None) -> Client:
    config = _load_supabase_config(secrets_path_override=secrets_path_override)
    key = config.get(key_name)
    if not key:
        raise KeyError(f"Missing '{key_name}' in Supabase configuration")
    return create_client(config["url"], key)


def get_supabase_admin_client(secrets_path_override: str | None = None) -> Client:
    """
    Return the server-only Supabase client for scraper writes and privileged backend actions.
    """
    return _create_supabase_client("service_role_key", secrets_path_override=secrets_path_override)


def get_supabase_backend_read_client(secrets_path_override: str | None = None) -> Client:
    """
    Return the private backend dashboard/read client.
    """
    return _create_supabase_client("service_role_key", secrets_path_override=secrets_path_override)


def get_supabase_client(secrets_path_override: str | None = None) -> Client:
    """
    Backward-compatible wrapper for legacy imports.

    Runtime code should prefer:
    - get_supabase_admin_client()
    - get_supabase_backend_read_client()
    """
    return get_supabase_backend_read_client(secrets_path_override=secrets_path_override)


if __name__ == "__main__":
    from pprint import pprint

    try:
        supabase = get_supabase_backend_read_client()
        print("✅ Connected to Supabase successfully.")

        try:
            result = supabase.table("biwenger_current_team").select("*").limit(1).execute()
            print("📦 Sample query from 'biwenger_current_team' table succeeded.")
            pprint(result.data)
        except Exception as query_err:
            print("⚠️ Connection OK, but table query failed (maybe table doesn't exist yet):")
            print(query_err)

    except Exception as e:
        print("❌ Failed to connect to Supabase.")
        print(e)
