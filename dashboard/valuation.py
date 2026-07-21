"""
Pure player valuation helpers — no Streamlit, no Supabase dependency.

All functions accept a pandas DataFrame and return a new DataFrame with
additional computed columns. Nothing is mutated in place.

Columns added by ``enrich_player_stats``:
    points_per_100k             — cumulative efficiency to date
    participation_rate          — matches_played / current_round
    current_round               — max(matches_played) across the DataFrame
    remaining_rounds            — TOTAL_SEASON_ROUNDS - current_round
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
    def _projected_per_100k(rate_series: pd.Series) -> pd.Series:
        """
        total_projected = points + average * rate * remaining_rounds
        projected_per_100k = total_projected / value * 100_000
        """
        projected_remaining = out["average"] * rate_series * remaining_rounds
        total_projected = out["points"] + projected_remaining
        return (_safe_div(total_projected, out["value"]) * 100_000).round(2)

    base_rate = out["participation_rate"]
    pessimistic_rate = (base_rate * 0.5).clip(upper=1.0)
    optimistic_rate = (base_rate * 1.5).clip(upper=1.0)

    out["projected_pts_per_100k_base"] = _projected_per_100k(base_rate)
    out["projected_pts_per_100k_pessimistic"] = _projected_per_100k(pessimistic_rate)
    out["projected_pts_per_100k_optimistic"] = _projected_per_100k(optimistic_rate)

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
