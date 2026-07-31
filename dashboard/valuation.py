"""
Pure player valuation helpers — no Streamlit, no Supabase dependency.

All functions accept a pandas DataFrame and return a new DataFrame with
additional computed columns. Nothing is mutated in place.

Columns added by ``enrich_player_stats``:
    points_per_100k             — cumulative efficiency to date
    participation_rate          — matches_played / current_round
    current_round               — max(matches_played) across the DataFrame
    remaining_rounds            — TOTAL_SEASON_ROUNDS - current_round
    projected_points_base                — base-rate season projection
    projected_points_pessimistic         — 50% of base participation rate
    projected_points_optimistic          — 150% of base participation rate (capped at 100%)
    projected_pts_per_100k_base         — base-rate projection
    projected_pts_per_100k_pessimistic  — 50% of base rate
    projected_pts_per_100k_optimistic   — 150% of base rate (capped at 100%)
    position_display            — human-readable position label
"""

import numpy as np
import pandas as pd

# ── Constants ────────────────────────────────────────────────────────────────

TOTAL_SEASON_ROUNDS: int = 38  # La Liga — easy to change for other leagues

# Canonical position labels used by the scatter (colour-keyed).
POSITION_MAP: dict[str, str] = {
    "Goalkeeper": "Goalkeeper",
    "Defender": "Defender",
    "Midfielder": "Midfielder",
    "Forward": "Forward",
}

POSITION_COLOURS: dict[str, str] = {
    "Goalkeeper": "#f59e0b",  # amber
    "Defender": "#2563eb",  # blue
    "Midfielder": "#16a34a",  # green
    "Forward": "#dc2626",  # red
}

POSITION_ORDER: list[str] = ["Goalkeeper", "Defender", "Midfielder", "Forward"]


# ── Core computation ─────────────────────────────────────────────────────────


def _safe_div(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """Divide element-wise, returning NaN where denominator is zero or null."""
    denom = denominator.replace(0, np.nan)
    return numerator / denom


def fair_value_from_points(points: float | int, target_points_per_100k: float | int) -> float:
    """Return the market value implied by a points target and efficiency anchor."""
    if pd.isna(points) or pd.isna(target_points_per_100k) or float(target_points_per_100k) <= 0:
        return np.nan
    return float(points) / float(target_points_per_100k) * 100_000


def enrich_player_stats(
    df: pd.DataFrame,
    *,
    total_rounds: int = TOTAL_SEASON_ROUNDS,
) -> pd.DataFrame:
    """
    Add valuation columns to a player-stats DataFrame.

    Required input columns:
        points, value, average, matches_played

    All added columns are described in the module docstring.
    Returns a new DataFrame (input is not mutated).
    """
    required = {"points", "value", "average", "matches_played"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"enrich_player_stats: missing columns {missing}")

    out = df.copy()

    # ── numeric coercion ─────────────────────────────────────────────────────
    for col in ("points", "value", "average", "matches_played"):
        out[col] = pd.to_numeric(out[col], errors="coerce")

    # ── efficiency to date ───────────────────────────────────────────────────
    out["points_per_100k"] = (_safe_div(out["points"], out["value"]) * 100_000).round(2)

    # ── participation rate ───────────────────────────────────────────────────
    current_round = int(out["matches_played"].max()) if not out.empty else 0
    out["current_round"] = current_round
    remaining_rounds = max(total_rounds - current_round, 0)
    out["remaining_rounds"] = remaining_rounds
    out["participation_rate"] = (
        (out["matches_played"] / current_round).round(4) if current_round > 0 else pd.Series(np.nan, index=out.index)
    )

    # ── projected points per 100k (three scenarios) ──────────────────────────
    def _projected_points(rate_series: pd.Series) -> pd.Series:
        projected_remaining = out["average"] * rate_series * remaining_rounds
        return (out["points"] + projected_remaining).round(2)

    base_rate = out["participation_rate"]
    pessimistic_rate = (base_rate * 0.5).clip(upper=1.0)
    optimistic_rate = (base_rate * 1.5).clip(upper=1.0)

    out["projected_points_base"] = _projected_points(base_rate)
    out["projected_points_pessimistic"] = _projected_points(pessimistic_rate)
    out["projected_points_optimistic"] = _projected_points(optimistic_rate)

    out["projected_pts_per_100k_base"] = (_safe_div(out["projected_points_base"], out["value"]) * 100_000).round(2)
    out["projected_pts_per_100k_pessimistic"] = (
        _safe_div(out["projected_points_pessimistic"], out["value"]) * 100_000
    ).round(2)
    out["projected_pts_per_100k_optimistic"] = (
        _safe_div(out["projected_points_optimistic"], out["value"]) * 100_000
    ).round(2)

    # ── position display label ───────────────────────────────────────────────
    if "position" in out.columns:
        out["position_display"] = out["position"].map(POSITION_MAP).fillna(out["position"])

    return out


# ── Current-team join helper ─────────────────────────────────────────────────


def mark_current_team(
    stats_df: pd.DataFrame,
    current_team_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Add a boolean ``is_current_team`` column to ``stats_df``.

    Matching is done by slug where both sides have a non-null slug; falls back
    to player_name when slugs are absent.

    Returns a new DataFrame (inputs are not mutated).
    """
    out = stats_df.copy()
    out["is_current_team"] = False

    if current_team_df.empty:
        return out

    # Build sets for fast lookup
    team_slugs: set[str] = set()
    team_names: set[str] = set()

    if "slug" in current_team_df.columns:
        team_slugs = set(current_team_df["slug"].dropna().str.strip().unique())
    if "name" in current_team_df.columns:
        team_names = set(current_team_df["name"].dropna().str.strip().unique())
    elif "player_name" in current_team_df.columns:
        team_names = set(current_team_df["player_name"].dropna().str.strip().unique())

    def _is_team(row: pd.Series) -> bool:
        slug = str(row.get("slug") or "").strip()
        name = str(row.get("player_name") or "").strip()
        if slug and team_slugs and slug in team_slugs:
            return True
        return bool(name and name in team_names)

    out["is_current_team"] = out.apply(_is_team, axis=1)
    return out


def build_points_cohort(
    stats_df: pd.DataFrame,
    *,
    selected_index: int,
    neighbors_each_side: int = 10,
) -> tuple[pd.Series, pd.DataFrame]:
    """
    Return the selected player row and a same-position comparison cohort.

    The cohort includes the selected player plus up to ``neighbors_each_side``
    players immediately above and below on total points.
    """
    required = {"player_name", "team", "position_display", "points", "value", "points_per_100k"}
    missing = required - set(stats_df.columns)
    if missing:
        raise ValueError(f"build_points_cohort: missing columns {missing}")
    if selected_index not in stats_df.index:
        raise KeyError(f"build_points_cohort: selected index {selected_index} not found")

    selected_row = stats_df.loc[selected_index]
    position_value = selected_row["position_display"]

    same_position = (
        stats_df[stats_df["position_display"] == position_value]
        .copy()
        .reset_index()
        .rename(columns={"index": "source_index"})
        .sort_values(["points", "value", "player_name"], ascending=[True, True, True], kind="mergesort")
        .reset_index(drop=True)
    )
    selected_pos = same_position.index[same_position["source_index"] == selected_index]
    if len(selected_pos) == 0:
        raise KeyError(f"build_points_cohort: selected index {selected_index} not found in same-position slice")
    selected_pos = int(selected_pos[0])

    lower_slice = same_position.iloc[max(0, selected_pos - neighbors_each_side) : selected_pos].copy()
    upper_slice = same_position.iloc[selected_pos + 1 : selected_pos + 1 + neighbors_each_side].copy()
    selected_slice = same_position.iloc[[selected_pos]].copy()

    lower_slice["cohort_band"] = "Below"
    selected_slice["cohort_band"] = "Selected"
    upper_slice["cohort_band"] = "Above"

    cohort = pd.concat([upper_slice, selected_slice, lower_slice], ignore_index=True)
    cohort["points_gap"] = (cohort["points"] - float(selected_row["points"])).round(2)
    cohort["value_gap"] = (cohort["value"] - float(selected_row["value"])).round(0)
    cohort["is_selected_player"] = cohort["cohort_band"] == "Selected"
    cohort["display_label"] = cohort["player_name"].astype(str) + " (" + cohort["team"].astype(str) + ")"
    cohort = cohort.sort_values(["points", "value", "player_name"], ascending=[False, True, True]).reset_index(drop=True)
    return selected_row.copy(), cohort


def summarize_points_cohort(selected_row: pd.Series, cohort_df: pd.DataFrame) -> dict[str, float]:
    """Return summary valuation anchors for a selected player and comparison cohort."""
    comparables = cohort_df[~cohort_df["is_selected_player"]].copy()
    valid_efficiency = comparables["points_per_100k"].dropna()

    cohort_target = float(valid_efficiency.median()) if not valid_efficiency.empty else np.nan
    fair_value_current = fair_value_from_points(selected_row.get("points"), cohort_target)
    fair_value_base = fair_value_from_points(selected_row.get("projected_points_base"), cohort_target)
    fair_value_optimistic = fair_value_from_points(selected_row.get("projected_points_optimistic"), cohort_target)

    return {
        "cohort_size": float(len(comparables)),
        "cohort_median_value": float(comparables["value"].median()) if not comparables.empty else np.nan,
        "cohort_mean_value": float(comparables["value"].mean()) if not comparables.empty else np.nan,
        "cohort_median_points_per_100k": cohort_target,
        "selected_points_per_100k": float(selected_row.get("points_per_100k", np.nan)),
        "selected_value": float(selected_row.get("value", np.nan)),
        "selected_points": float(selected_row.get("points", np.nan)),
        "fair_value_current_points": fair_value_current,
        "fair_value_projected_base": fair_value_base,
        "fair_value_projected_optimistic": fair_value_optimistic,
        "base_projection_points": float(selected_row.get("projected_points_base", np.nan)),
        "optimistic_projection_points": float(selected_row.get("projected_points_optimistic", np.nan)),
        "market_delta_vs_base_fair": float(selected_row.get("value", np.nan) - fair_value_base)
        if pd.notna(fair_value_base)
        else np.nan,
    }


def build_price_simulation_table(
    selected_row: pd.Series,
    *,
    bid_deltas: list[int | float],
    point_scenarios: list[tuple[str, int | float]],
    cohort_target_points_per_100k: float | int,
) -> pd.DataFrame:
    """Return a wide scenario table with one row per points scenario."""
    current_value = float(selected_row.get("value", np.nan))
    target_efficiency = float(cohort_target_points_per_100k) if pd.notna(cohort_target_points_per_100k) else np.nan

    price_points = [("Current", current_value)]
    for delta in bid_deltas:
        if pd.isna(delta):
            continue
        price_points.append((f"+€{int(delta):,}", current_value + float(delta)))

    deduped_prices: list[tuple[str, float]] = []
    seen_prices: set[float] = set()
    for label, price in price_points:
        rounded_price = round(price, 2)
        if rounded_price in seen_prices:
            continue
        seen_prices.add(rounded_price)
        deduped_prices.append((label, rounded_price))

    rows: list[dict[str, float | str]] = []
    for scenario_label, points_value in point_scenarios:
        row: dict[str, float | str] = {
            "Scenario": scenario_label,
            "Projected points": float(points_value),
            "Fair value @ cohort median": fair_value_from_points(points_value, target_efficiency),
        }
        for price_label, price in deduped_prices:
            row[f"{price_label} pts/100k"] = np.nan if price <= 0 else round(float(points_value) / price * 100_000, 2)
        rows.append(row)

    return pd.DataFrame(rows)
