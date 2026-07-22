import pandas as pd
import pytest

from scraping_biwenger.players.persist import persist_player_matches, persist_player_stats, persist_player_values
from scraping_biwenger.players.repository import delete_matches_for_season_identities, delete_stats_snapshot
from scraping_biwenger.players.transform import PLAYER_MATCHES_COLUMNS, PLAYER_STATS_COLUMNS, PLAYER_VALUE_COLUMNS


class FakeQuery:
    def __init__(self, table_name, operations, select_data=None):
        self.table_name = table_name
        self.operations = operations
        self.select_data = select_data or []
        self.filters = []

    def select(self, columns):
        self.operations.append(
            {
                "table": self.table_name,
                "action": "select",
                "columns": columns,
                "filters": self.filters,
            }
        )
        return self

    def delete(self):
        self.operations.append({"table": self.table_name, "action": "delete", "filters": self.filters})
        return self

    def insert(self, rows, returning=None):
        self.operations.append(
            {
                "table": self.table_name,
                "action": "insert",
                "rows": rows,
                "returning": returning,
            }
        )
        return self

    def upsert(self, rows, on_conflict=None, returning=None):
        self.operations.append(
            {
                "table": self.table_name,
                "action": "upsert",
                "rows": rows,
                "on_conflict": on_conflict,
                "returning": returning,
            }
        )
        return self

    def eq(self, column, value):
        self.filters.append(("eq", column, value))
        return self

    def in_(self, column, values):
        self.filters.append(("in", column, values))
        return self

    def gte(self, column, value):
        self.filters.append(("gte", column, value))
        return self

    def lte(self, column, value):
        self.filters.append(("lte", column, value))
        return self

    def range(self, start, end):
        self.filters.append(("range", start, end))
        return self

    def execute(self):
        return type("Result", (), {"data": self.select_data})()


class FakeSupabase:
    def __init__(self, select_data=None):
        self.operations = []
        self.select_data = select_data or []

    def table(self, table_name):
        return FakeQuery(table_name, self.operations, self.select_data)


def test_delete_matches_for_season_identities_filters_full_season_aware_key():
    supabase = FakeSupabase()

    delete_matches_for_season_identities(
        supabase,
        "biwenger_player_matches",
        [
            {
                "slug": "mbappe",
                "season_label": "2025/2026",
                "round_label": "R1",
                "match_date": "2025-08-19",
                "scoring_system": "sofascore",
            }
        ],
    )

    delete_op = supabase.operations[0]
    assert delete_op["action"] == "delete"
    assert set(delete_op["filters"]) == {
        ("eq", "slug", "mbappe"),
        ("eq", "season_label", "2025/2026"),
        ("eq", "round_label", "R1"),
        ("eq", "match_date", "2025-08-19"),
        ("eq", "scoring_system", "sofascore"),
    }


def test_delete_stats_snapshot_filters_slug_snapshot_identity():
    supabase = FakeSupabase()

    delete_stats_snapshot(
        supabase,
        "biwenger_player_stats",
        "mbappe",
        "2026-07-22",
        "sofascore",
    )

    delete_op = supabase.operations[0]
    assert delete_op["action"] == "delete"
    assert set(delete_op["filters"]) == {
        ("eq", "slug", "mbappe"),
        ("eq", "as_of_date", "2026-07-22"),
        ("eq", "scoring_system", "sofascore"),
    }


def test_persist_player_stats_upserts_rows_by_snapshot_identity():
    supabase = FakeSupabase()
    stats_df = pd.DataFrame(
        [
            {
                "player_name": "Mbappé",
                "team": "Real Madrid",
                "slug": "mbappe",
                "position": "Forward",
                "status": "Fit",
                "status_detail": None,
                "scoring_system": "sofascore",
                "points": 10,
                "value": 1000000,
                "min_value": 900000,
                "max_value": 1100000,
                "matches_played": 1,
                "average": 10.0,
                "market_purchases_pct": 0.0,
                "market_sales_pct": 0.0,
                "market_usage_pct": 0.0,
                "season": "2025/2026",
                "as_of_date": "2026-07-22",
            }
        ],
        columns=PLAYER_STATS_COLUMNS,
    )

    persist_player_stats(stats_df, supabase=supabase)

    upsert_op = next(op for op in supabase.operations if op["action"] == "upsert")
    assert upsert_op["on_conflict"] == "slug,as_of_date,scoring_system"
    assert len(upsert_op["rows"]) == 1
    assert not any(op["action"] == "delete" for op in supabase.operations)


def test_persist_player_stats_rejects_missing_slug():
    supabase = FakeSupabase()
    stats_df = pd.DataFrame(
        [
            {
                "player_name": "Mbappé",
                "team": "Real Madrid",
                "slug": None,
                "position": "Forward",
                "status": "Fit",
                "status_detail": None,
                "scoring_system": "sofascore",
                "points": 10,
                "value": 1000000,
                "min_value": 900000,
                "max_value": 1100000,
                "matches_played": 1,
                "average": 10.0,
                "market_purchases_pct": 0.0,
                "market_sales_pct": 0.0,
                "market_usage_pct": 0.0,
                "season": "2025/2026",
                "as_of_date": "2026-07-22",
            }
        ],
        columns=PLAYER_STATS_COLUMNS,
    )

    with pytest.raises(ValueError, match="slug is required"):
        persist_player_stats(stats_df, supabase=supabase)


def test_persist_player_matches_upserts_rows_by_season_aware_identity():
    supabase = FakeSupabase()
    matches_df = pd.DataFrame(
        [
            {
                "season_label": "2025/2026",
                "round_label": "R1",
                "match_date": "2025-08-19",
                "points": 14,
                "best_xi": True,
                "events": "",
                "player_name": "Mbappé",
                "team": "Real Madrid",
                "slug": "mbappe",
                "scoring_system": "sofascore",
                "as_of_date": "2026-07-20",
            }
        ],
        columns=PLAYER_MATCHES_COLUMNS,
    )

    persist_player_matches(matches_df, supabase=supabase)

    upsert_op = next(op for op in supabase.operations if op["action"] == "upsert")
    assert upsert_op["on_conflict"] == "slug,season_label,round_label,match_date,scoring_system"
    assert len(upsert_op["rows"]) == 1
    assert not any(op["action"] == "delete" for op in supabase.operations)


def test_persist_player_matches_rejects_missing_slug():
    supabase = FakeSupabase()
    matches_df = pd.DataFrame(
        [
            {
                "season_label": "2025/2026",
                "round_label": "R1",
                "match_date": "2025-08-19",
                "points": 14,
                "best_xi": True,
                "events": "",
                "player_name": "Mbappé",
                "team": "Real Madrid",
                "slug": None,
                "scoring_system": "sofascore",
                "as_of_date": "2026-07-20",
            }
        ],
        columns=PLAYER_MATCHES_COLUMNS,
    )

    with pytest.raises(ValueError, match="slug is required"):
        persist_player_matches(matches_df, supabase=supabase)


def test_persist_player_matches_rejects_missing_match_identity_values():
    supabase = FakeSupabase()
    matches_df = pd.DataFrame(
        [
            {
                "season_label": "2025/2026",
                "round_label": None,
                "match_date": "2025-08-19",
                "points": 14,
                "best_xi": True,
                "events": "",
                "player_name": "Mbappé",
                "team": "Real Madrid",
                "slug": "mbappe",
                "scoring_system": "sofascore",
                "as_of_date": "2026-07-20",
            }
        ],
        columns=PLAYER_MATCHES_COLUMNS,
    )

    with pytest.raises(ValueError, match="required identity values"):
        persist_player_matches(matches_df, supabase=supabase)


def test_persist_player_values_inserts_new_rows_and_replaces_changed_rows_only():
    supabase = FakeSupabase(
        select_data=[
            {"date": "2026-01-01", "market_value_eur": 100},
            {"date": "2026-01-02", "market_value_eur": 150},
        ]
    )
    value_df = pd.DataFrame(
        [
            {
                "slug": "mbappe",
                "player_name": "Mbappé",
                "team": "Real Madrid",
                "date": "2026-01-01",
                "market_value_eur": 100,
            },
            {
                "slug": "mbappe",
                "player_name": "Mbappé",
                "team": "Real Madrid",
                "date": "2026-01-02",
                "market_value_eur": 155,
            },
            {
                "slug": "mbappe",
                "player_name": "Mbappé",
                "team": "Real Madrid",
                "date": "2026-01-03",
                "market_value_eur": 200,
            },
        ],
        columns=PLAYER_VALUE_COLUMNS,
    )

    persist_player_values(value_df, supabase=supabase)

    delete_op = next(op for op in supabase.operations if op["action"] == "delete")
    assert ("eq", "slug", "mbappe") in delete_op["filters"]
    assert ("in", "date", ["2026-01-02"]) in delete_op["filters"]

    insert_op = next(op for op in supabase.operations if op["action"] == "insert")
    inserted_dates = {row["date"] for row in insert_op["rows"]}
    assert inserted_dates == {"2026-01-02", "2026-01-03"}
