import dashboard.queries as queries


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def select(self, _columns):
        return self

    def eq(self, _column, _value):
        return self

    def order(self, _column, desc=False):
        return self

    def execute(self):
        return type("Result", (), {"data": self.rows})()


class FakeSupabase:
    def __init__(self, rows):
        self.rows = rows

    def table(self, _table_name):
        return FakeQuery(self.rows)


def test_fetch_all_player_stats_handles_all_slugged_rows_without_keyerror():
    supabase = FakeSupabase(
        [
            {
                "slug": "mbappe",
                "player_name": "Mbappe",
                "team": "Real Madrid",
                "position": "Forward",
                "points": 100,
                "value": 10000000,
                "average": 5.0,
                "matches_played": 20,
                "as_of_date": "2026-07-31",
                "scoring_system": "sofascore",
            },
            {
                "slug": "pedri",
                "player_name": "Pedri",
                "team": "Barcelona",
                "position": "Midfielder",
                "points": 90,
                "value": 9000000,
                "average": 4.5,
                "matches_played": 20,
                "as_of_date": "2026-07-30",
                "scoring_system": "sofascore",
            },
        ]
    )

    df = queries.fetch_all_player_stats(supabase=supabase)

    assert df["slug"].tolist() == ["mbappe", "pedri"]
    assert "as_of_date" in df.columns


def test_fetch_all_player_stats_dedupes_legacy_rows_after_slug_match():
    supabase = FakeSupabase(
        [
            {
                "slug": "mbappe",
                "player_name": "Mbappe",
                "team": "Real Madrid",
                "position": "Forward",
                "points": 100,
                "value": 10000000,
                "average": 5.0,
                "matches_played": 20,
                "as_of_date": "2026-07-31",
                "scoring_system": "sofascore",
            },
            {
                "slug": None,
                "player_name": "Mbappe",
                "team": "Real Madrid",
                "position": "Forward",
                "points": 95,
                "value": 10000000,
                "average": 4.8,
                "matches_played": 19,
                "as_of_date": "2026-07-30",
                "scoring_system": "sofascore",
            },
            {
                "slug": None,
                "player_name": "Lamine Yamal",
                "team": "Barcelona",
                "position": "Forward",
                "points": 80,
                "value": 8000000,
                "average": 4.0,
                "matches_played": 18,
                "as_of_date": "2026-07-29",
                "scoring_system": "sofascore",
            },
        ]
    )

    df = queries.fetch_all_player_stats(supabase=supabase)

    assert set(df["player_name"]) == {"Mbappe", "Lamine Yamal"}
    assert len(df) == 2
