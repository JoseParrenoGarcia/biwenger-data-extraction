import dashboard.queries as queries


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows
        self.selected_columns = None

    def select(self, columns):
        if columns != "*":
            self.selected_columns = [column.strip() for column in columns.split(",")]
        return self

    def eq(self, column, value):
        self.rows = [row for row in self.rows if row.get(column) == value]
        return self

    def in_(self, column, values):
        self.rows = [row for row in self.rows if row.get(column) in values]
        return self

    def gte(self, column, value):
        self.rows = [row for row in self.rows if row.get(column) >= value]
        return self

    def lte(self, column, value):
        self.rows = [row for row in self.rows if row.get(column) <= value]
        return self

    def order(self, column, desc=False):
        self.rows = sorted(self.rows, key=lambda row: row.get(column), reverse=desc)
        return self

    def range(self, start, end):
        self.rows = self.rows[start : end + 1]
        return self

    def execute(self):
        if self.selected_columns is not None:
            rows = [{column: row.get(column) for column in self.selected_columns} for row in self.rows]
        else:
            rows = self.rows
        return type("Result", (), {"data": rows})()


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


def test_fetch_all_player_stats_filters_to_latest_snapshot_for_selected_season():
    supabase = FakeSupabase(
        [
            {
                "slug": "mbappe",
                "player_name": "Mbappe",
                "team": "Real Madrid",
                "position": "Forward",
                "points": 120,
                "value": 10000000,
                "average": 6.0,
                "matches_played": 20,
                "season": "2025/2026 season",
                "as_of_date": "2026-05-30",
                "scoring_system": "sofascore",
            },
            {
                "slug": "mbappe",
                "player_name": "Mbappe",
                "team": "Real Madrid",
                "position": "Forward",
                "points": 12,
                "value": 11000000,
                "average": 4.0,
                "matches_played": 3,
                "season": "2026/2027 season",
                "as_of_date": "2026-08-15",
                "scoring_system": "sofascore",
            },
            {
                "slug": "pedri",
                "player_name": "Pedri",
                "team": "Barcelona",
                "position": "Midfielder",
                "points": 92,
                "value": 9000000,
                "average": 5.0,
                "matches_played": 19,
                "season": "2025/2026 season",
                "as_of_date": "2026-05-29",
                "scoring_system": "sofascore",
            },
        ]
    )

    df = queries.fetch_all_player_stats(supabase=supabase, season="2025/2026 season")

    assert df["slug"].tolist() == ["mbappe", "pedri"]
    assert df.set_index("slug").loc["mbappe", "points"] == 120
    assert set(df["season"]) == {"2025/2026 season"}


def test_fetch_player_stat_seasons_returns_latest_date_per_season():
    supabase = FakeSupabase(
        [
            {"season": "2026/2027 season", "as_of_date": "2026-08-15", "scoring_system": "sofascore"},
            {"season": "2026/2027 season", "as_of_date": "2026-08-15", "scoring_system": "sofascore"},
            {"season": "2025/2026 season", "as_of_date": "2026-05-30", "scoring_system": "sofascore"},
        ]
    )

    df = queries.fetch_player_stat_seasons(supabase=supabase)

    assert list(zip(df["season"], df["as_of_date"].dt.date.astype(str))) == [
        ("2026/2027 season", "2026-08-15"),
        ("2025/2026 season", "2026-05-30"),
    ]


def test_fetch_stats_history_for_slugs_returns_all_rows_despite_name_variants():
    """Regression: Biwenger sometimes changes the displayed player_name (e.g.
    'Canales' → 'Sergio Canales'). The query must filter by slug so that all
    historical snapshots are returned, not just the latest-name rows."""
    supabase = FakeSupabase(
        [
            {
                "slug": "canales",
                "player_name": "Canales",
                "team": "Racing",
                "as_of_date": "2026-07-21",
                "scoring_system": "sofascore",
                "market_purchases_pct": 53.0,
                "market_sales_pct": 9.0,
            },
            {
                "slug": "canales",
                "player_name": "Canales",
                "team": "Racing",
                "as_of_date": "2026-08-01",
                "scoring_system": "sofascore",
                "market_purchases_pct": 61.0,
                "market_sales_pct": 2.0,
            },
            {
                "slug": "canales",
                "player_name": "Sergio Canales",
                "team": "Racing",
                "as_of_date": "2026-09-08",
                "scoring_system": "sofascore",
                "market_purchases_pct": 32.0,
                "market_sales_pct": 1.0,
            },
        ]
    )

    df = queries.fetch_stats_history_for_slugs(["canales"], supabase=supabase)

    assert len(df) == 3
    assert set(df["player_name"]) == {"Canales", "Sergio Canales"}
    assert df["slug"].tolist() == ["canales", "canales", "canales"]
