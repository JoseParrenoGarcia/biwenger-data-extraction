import dashboard.queries as queries


def test_dashboard_queries_use_backend_read_client(monkeypatch):
    sentinel = object()
    monkeypatch.setattr(queries, "get_supabase_backend_read_client", lambda: sentinel)

    assert queries._client() is sentinel
