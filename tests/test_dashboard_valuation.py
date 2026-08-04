"""
Unit tests for dashboard/valuation.py — no Streamlit, no Supabase.
"""

import pandas as pd
import pytest

from dashboard.valuation import (
    build_points_cohort,
    build_price_simulation_table,
    enrich_player_stats,
    fair_value_from_points,
    mark_current_team,
    summarize_points_cohort,
)

# ── Fixtures ─────────────────────────────────────────────────────────────────


def _base_row(**kwargs) -> dict:
    defaults = {
        "player_name": "Test Player",
        "team": "Test FC",
        "slug": "test-player",
        "position": "Forward",
        "points": 100,
        "value": 10_000_000,
        "average": 5.0,
        "matches_played": 20,
    }
    defaults.update(kwargs)
    return defaults


def _df(*rows) -> pd.DataFrame:
    return pd.DataFrame([_base_row(**r) for r in rows])


# ── enrich_player_stats: basic output ─────────────────────────────────────────


def test_points_per_100k_basic():
    df = enrich_player_stats(_df({"points": 200, "value": 20_000_000}))
    assert df["points_per_100k"].iloc[0] == pytest.approx(1.0)


def test_points_per_100k_with_different_values():
    df = enrich_player_stats(_df({"points": 50, "value": 5_000_000}))
    assert df["points_per_100k"].iloc[0] == pytest.approx(1.0)


def test_participation_rate_basic():
    # matches_played=20, current_round=max=20 → rate = 1.0
    df = enrich_player_stats(_df({"matches_played": 20}))
    assert df["participation_rate"].iloc[0] == pytest.approx(1.0)


def test_participation_rate_partial():
    # Two players: 10 and 20 games. current_round = 20.
    rows = [{"matches_played": 10}, {"matches_played": 20}]
    df = enrich_player_stats(pd.DataFrame([_base_row(**r) for r in rows]))
    assert df["current_round"].iloc[0] == 20
    assert df["participation_rate"].iloc[0] == pytest.approx(0.5)
    assert df["participation_rate"].iloc[1] == pytest.approx(1.0)


def test_remaining_rounds():
    df = enrich_player_stats(_df({"matches_played": 20}), total_rounds=38)
    assert df["remaining_rounds"].iloc[0] == 18


def test_remaining_rounds_no_negative():
    # matches_played > total_rounds shouldn't produce negative remaining
    df = enrich_player_stats(_df({"matches_played": 40}), total_rounds=38)
    assert df["remaining_rounds"].iloc[0] == 0


def test_fair_value_from_points():
    assert fair_value_from_points(140, 7.0) == pytest.approx(2_000_000.0)


# ── enrich_player_stats: projected metrics ────────────────────────────────────


def test_projected_base_equals_pessimistic_times_two_roughly():
    # Use matches_played=10 out of max=20 so participation_rate=0.5,
    # optimistic=0.75 > base=0.5 > pessimistic=0.25 (no cap triggered).
    rows = [{"matches_played": 10}, {"matches_played": 20}]
    df = enrich_player_stats(pd.DataFrame([_base_row(**r) for r in rows]))
    base = df["projected_pts_per_100k_base"].iloc[0]
    pess = df["projected_pts_per_100k_pessimistic"].iloc[0]
    opti = df["projected_pts_per_100k_optimistic"].iloc[0]
    assert pess < base < opti


def test_projected_pessimistic_is_half_base_rate(tmp_path):
    # participation_rate=0.5 → pessimistic uses 0.25, base uses 0.5
    rows = [{"matches_played": 10}, {"matches_played": 20}]  # current_round=20, rate=0.5 for row0
    df = enrich_player_stats(pd.DataFrame([_base_row(**r) for r in rows]))
    row = df.iloc[0]
    rate_base = row["participation_rate"]  # 0.5
    rate_pess = rate_base * 0.5  # 0.25
    remaining = row["remaining_rounds"]  # 18
    avg = row["average"]
    val = row["value"]
    pts = row["points"]
    expected_base = round((pts + avg * rate_base * remaining) / val * 100_000, 2)
    expected_pess = round((pts + avg * rate_pess * remaining) / val * 100_000, 2)
    assert df["projected_pts_per_100k_base"].iloc[0] == pytest.approx(expected_base, abs=0.01)
    assert df["projected_pts_per_100k_pessimistic"].iloc[0] == pytest.approx(expected_pess, abs=0.01)
    expected_base_points = round(pts + avg * rate_base * remaining, 2)
    expected_pess_points = round(pts + avg * rate_pess * remaining, 2)
    assert df["projected_points_base"].iloc[0] == pytest.approx(expected_base_points, abs=0.01)
    assert df["projected_points_pessimistic"].iloc[0] == pytest.approx(expected_pess_points, abs=0.01)


def test_optimistic_rate_capped_at_1():
    # Player already at 90% rate → optimistic would be 135%, must cap at 100%
    rows = [{"matches_played": 18}, {"matches_played": 20}]  # rate=0.9, opti=min(1.35,1)=1.0
    df = enrich_player_stats(pd.DataFrame([_base_row(**r) for r in rows]))
    # Manually check the cap
    rate = df["participation_rate"].iloc[0]  # 0.9
    assert rate * 1.5 > 1.0  # confirms the cap would trigger
    remaining = df["remaining_rounds"].iloc[0]
    avg = df["average"].iloc[0]
    val = df["value"].iloc[0]
    pts = df["points"].iloc[0]
    expected_opti = round((pts + avg * min(rate * 1.5, 1.0) * remaining) / val * 100_000, 2)
    assert df["projected_pts_per_100k_optimistic"].iloc[0] == pytest.approx(expected_opti, abs=0.01)


# ── enrich_player_stats: edge cases ───────────────────────────────────────────


def test_zero_matches_played_gives_zero_participation():
    df = enrich_player_stats(_df({"matches_played": 0}))
    assert df["participation_rate"].iloc[0] == pytest.approx(0.0) or pd.isna(df["participation_rate"].iloc[0])


def test_zero_value_gives_null_per_100k():
    df = enrich_player_stats(_df({"value": 0}))
    assert pd.isna(df["points_per_100k"].iloc[0])
    assert pd.isna(df["projected_pts_per_100k_base"].iloc[0])


def test_missing_required_column_raises():
    with pytest.raises(ValueError, match="missing columns"):
        enrich_player_stats(pd.DataFrame([{"player_name": "X", "points": 10}]))


def test_input_not_mutated():
    original = _df({"points": 100, "value": 10_000_000})
    original_cols = set(original.columns)
    enrich_player_stats(original)
    assert set(original.columns) == original_cols


def test_empty_dataframe_returns_empty():
    empty = pd.DataFrame(
        columns=["player_name", "team", "slug", "position", "points", "value", "average", "matches_played"]
    )
    result = enrich_player_stats(empty)
    assert result.empty


# ── mark_current_team ─────────────────────────────────────────────────────────


def test_mark_current_team_by_slug():
    stats = _df({"slug": "mbappe"}, {"slug": "pedri"})
    team = pd.DataFrame([{"slug": "mbappe", "name": "Mbappé"}])
    result = mark_current_team(stats, team)
    assert result["is_current_team"].tolist() == [True, False]


def test_mark_current_team_by_name_fallback():
    stats = _df({"slug": None, "player_name": "Pedri"}, {"slug": None, "player_name": "Mbappé"})
    team = pd.DataFrame([{"name": "Pedri"}])
    result = mark_current_team(stats, team)
    assert result["is_current_team"].tolist() == [True, False]


def test_mark_current_team_empty_team():
    stats = _df({"slug": "mbappe"})
    result = mark_current_team(stats, pd.DataFrame())
    assert result["is_current_team"].tolist() == [False]


def test_mark_current_team_does_not_mutate():
    stats = _df({"slug": "mbappe"})
    team = pd.DataFrame([{"slug": "mbappe", "name": "Mbappé"}])
    mark_current_team(stats, team)
    assert "is_current_team" not in stats.columns


def test_build_points_cohort_uses_same_position_and_neighbors():
    rows = []
    for i, points in enumerate([80, 90, 100, 110, 120, 130, 140]):
        rows.append(
            {
                "player_name": f"Def {i}",
                "team": f"Team {i}",
                "slug": f"def-{i}",
                "position": "Defender",
                "points": points,
                "value": 1_000_000 + i * 100_000,
                "average": 4.0,
                "matches_played": 20,
            }
        )
    rows.append(
        {
            "player_name": "Fwd 1",
            "team": "Other",
            "slug": "fwd-1",
            "position": "Forward",
            "points": 999,
            "value": 9_000_000,
            "average": 8.0,
            "matches_played": 20,
        }
    )

    df = enrich_player_stats(pd.DataFrame(rows))
    selected_index = df.index[df["player_name"] == "Def 3"][0]

    selected_row, cohort = build_points_cohort(df, selected_index=selected_index, neighbors_each_side=2)

    assert selected_row["player_name"] == "Def 3"
    assert set(cohort["player_name"]) == {"Def 1", "Def 2", "Def 3", "Def 4", "Def 5"}
    assert "Fwd 1" not in set(cohort["player_name"])
    assert cohort["is_selected_player"].sum() == 1


def test_summarize_points_cohort_and_price_simulation():
    df = enrich_player_stats(
        pd.DataFrame(
            [
                _base_row(player_name="A", team="TA", slug="a", position="Defender", points=100, value=2_000_000),
                _base_row(player_name="B", team="TB", slug="b", position="Defender", points=110, value=2_000_000),
                _base_row(player_name="C", team="TC", slug="c", position="Defender", points=120, value=2_000_000),
                _base_row(player_name="D", team="TD", slug="d", position="Defender", points=130, value=2_000_000),
                _base_row(player_name="E", team="TE", slug="e", position="Defender", points=140, value=2_000_000),
            ]
        )
    )
    selected_index = df.index[df["player_name"] == "C"][0]
    selected_row, cohort = build_points_cohort(df, selected_index=selected_index, neighbors_each_side=2)
    summary = summarize_points_cohort(selected_row, cohort)

    assert summary["cohort_median_points_per_100k"] == pytest.approx(6.0)
    assert summary["fair_value_current_points"] == pytest.approx(2_000_000.0)

    sim = build_price_simulation_table(
        selected_row,
        bid_deltas=[200_000, 500_000],
        point_scenarios=[("Base", 120), ("Upside", 150)],
        cohort_target_points_per_100k=summary["cohort_median_points_per_100k"],
    )

    assert list(sim["Scenario"]) == ["Base", "Upside"]
    assert sim.loc[0, "Current pts/100k"] == pytest.approx(6.0)
    assert sim.loc[0, "+€200,000 pts/100k"] == pytest.approx(round(120 / 2_200_000 * 100_000, 2))
    assert sim.loc[1, "Fair value @ cohort median"] == pytest.approx(2_500_000.0)
