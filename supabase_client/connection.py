import os
import toml
from supabase import create_client, Client


def get_supabase_client(secrets_path_override: str = None) -> Client:
    """
    Loads Supabase credentials and returns an authenticated client instance.
    Optionally accepts a custom path for secrets file (for testing).
    """
    if secrets_path_override:
        secrets_path = secrets_path_override
    else:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        root_dir = os.path.abspath(os.path.join(current_dir, ".."))
        secrets_path = os.path.join(root_dir, "secrets", "supabase.toml")

    if not os.path.exists(secrets_path):
        raise FileNotFoundError(f"Missing secrets file at: {secrets_path}")

    config = toml.load(secrets_path)
    url = config["supabase"].get("url")
    key = config["supabase"].get("anon_key")

    if not url or not key:
        raise KeyError("Missing 'url' or 'anon_key' in supabase.toml")

    return create_client(url, key)


if __name__ == "__main__":
    from pprint import pprint

    try:
        supabase = get_supabase_client()
        print("✅ Connected to Supabase successfully.")

        # Minimal test: try selecting 0 rows from an active Biwenger table.
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
