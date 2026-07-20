import pandas as pd

from scraping_biwenger.players.persist import persist_player_matches
from scraping_biwenger.players.transform import PLAYER_MATCHES_COLUMNS
from supabase_client.utils import delete_matches_for_player_identities


class FakeQuery:
    def __init__(self, table_name, operations):
        self.table_name = table_name
        self.operations = operations
        self.filters = []

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

    def eq(self, column, value):
        self.filters.append(("eq", column, value))
        return self

    def in_(self, column, values):
        self.filters.append(("in", column, values))
        return self

    def execute(self):
        return type("Result", (), {"data": []})()


class FakeSupabase:
    def __init__(self):
        self.operations = []

    def table(self, table_name):
        return FakeQuery(table_name, self.operations)


def test_delete_matches_for_player_identities_filters_full_season_aware_key():
    supabase = FakeSupabase()

    delete_matches_for_player_identities(
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


def test_persist_player_matches_deletes_slugged_rows_by_season_aware_identity():
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

    delete_op = next(op for op in supabase.operations if op["action"] == "delete")
    assert set(delete_op["filters"]) == {
        ("eq", "slug", "mbappe"),
        ("eq", "season_label", "2025/2026"),
        ("eq", "round_label", "R1"),
        ("eq", "match_date", "2025-08-19"),
        ("eq", "scoring_system", "sofascore"),
    }
    insert_op = next(op for op in supabase.operations if op["action"] == "insert")
    assert len(insert_op["rows"]) == 1
