"""
Player Value Comparison page — issue #116.

Answers: which players produce enough points for their market value, and how
does my current team compare with the broader market?

Layout
------
Filters row   : Position (multiselect), Team (multiselect)
Highlight row : Player selector → gold-ring layer
Axis row      : x-axis, y-axis selectors + "Highlight my team only" toggle
Scatter chart : 3-layer rendering (background / team / selected)
Table         : same filtered players, sortable
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.data import load_all_player_stats, load_current_team
from dashboard.valuation import (
    POSITION_COLOURS,
    POSITION_ORDER,
    enrich_player_stats,
    mark_current_team,
)

st.set_page_config(layout="wide", page_title="Player Value Comparison")

# ── Constants ─────────────────────────────────────────────────────────────────

_TEAM_BORDER_COLOUR = "#111827"  # thick black → "I own this"
_SEL_BORDER_COLOUR = "#f59e0b"  # gold → "I'm looking at this"

_AXIS_OPTIONS: dict[str, str] = {
    "Market value (€)": "value",
    "Total points": "points",
    "Average pts/game": "average",
    "Pts per 100k": "points_per_100k",
    "Projected pts/100k (base)": "projected_pts_per_100k_base",
    "Participation rate": "participation_rate",
}

_TABLE_COLUMNS: list[str] = [
    "player_name",
    "team",
    "position_display",
    "matches_played",
    "participation_rate",
    "points",
    "average",
    "value",
    "points_per_100k",
    "projected_pts_per_100k_pessimistic",
    "projected_pts_per_100k_base",
    "projected_pts_per_100k_optimistic",
]

_TABLE_LABELS: dict[str, str] = {
    "player_name": "Player",
    "team": "Team",
    "position_display": "Position",
    "matches_played": "Games",
    "participation_rate": "Part. rate",
    "points": "Points",
    "average": "Avg pts/game",
    "value": "Value (€)",
    "points_per_100k": "Pts/100k",
    "projected_pts_per_100k_pessimistic": "Proj pessimistic",
    "projected_pts_per_100k_base": "Proj base",
    "projected_pts_per_100k_optimistic": "Proj optimistic",
}

# ── Data loading ──────────────────────────────────────────────────────────────


@st.cache_data(ttl=300)
def _load_enriched() -> pd.DataFrame:
    stats = load_all_player_stats()
    team = load_current_team()
    if stats.empty:
        return stats
    enriched = enrich_player_stats(stats)
    enriched = mark_current_team(enriched, team)
    return enriched


# ── Page ──────────────────────────────────────────────────────────────────────

st.title("Player Value Comparison")
st.caption("Who produces enough points for their price? Where does your squad stand?")

df_all = _load_enriched()

if df_all.empty:
    st.warning("No player stats available.")
    st.stop()

# ── Filters ───────────────────────────────────────────────────────────────────

col_pos, col_team, col_toggle = st.columns([2, 3, 1])

positions_available = [p for p in POSITION_ORDER if p in df_all["position_display"].unique()]
sel_positions = col_pos.multiselect("Position", positions_available, default=positions_available)

teams_available = sorted(df_all["team"].dropna().unique().tolist())
sel_teams = col_team.multiselect("Team", teams_available)

highlight_team_only = col_toggle.toggle("My squad only", value=False)

# ── Player highlight selector ─────────────────────────────────────────────────

player_labels = sorted(df_all["player_name"].dropna().unique().tolist())
sel_players = st.multiselect(
    "Highlight players (gold ring)",
    player_labels,
    placeholder="Search for a player…",
)

# ── Axis selectors ────────────────────────────────────────────────────────────

ax_col1, ax_col2 = st.columns(2)
axis_labels = list(_AXIS_OPTIONS.keys())
x_label = ax_col1.selectbox("X axis", axis_labels, index=0)
y_label = ax_col2.selectbox("Y axis", axis_labels, index=1)
x_col = _AXIS_OPTIONS[x_label]
y_col = _AXIS_OPTIONS[y_label]

# ── Filter data ───────────────────────────────────────────────────────────────

df = df_all.copy()
if sel_positions:
    df = df[df["position_display"].isin(sel_positions)]
if sel_teams:
    df = df[df["team"].isin(sel_teams)]

# Drop rows where x or y are null
df = df.dropna(subset=[x_col, y_col])

if df.empty:
    st.info("No players match the current filters.")
    st.stop()

# ── Build scatter ─────────────────────────────────────────────────────────────


def _tertile_lines(fig: go.Figure, series: pd.Series, axis: str) -> None:
    for q in (0.33, 0.67):
        val = series.quantile(q)
        if pd.notna(val) and np.isfinite(val):
            kwargs = dict(line_dash="dash", line_color="rgba(156,163,175,0.5)", line_width=1)
            if axis == "x":
                fig.add_vline(x=val, **kwargs)
            else:
                fig.add_hline(y=val, **kwargs)


def _hover_text(row: pd.Series) -> str:
    def _fmt(v, prefix="") -> str:
        if pd.isna(v):
            return "—"
        if prefix == "€":
            m = v / 1_000_000
            return f"€{m:.1f}M" if m >= 1 else f"€{v / 1000:.0f}k"
        return f"{v:.1f}" if isinstance(v, float) else str(v)

    proj_range = (
        f"{_fmt(row.get('projected_pts_per_100k_pessimistic'))} / "
        f"{_fmt(row.get('projected_pts_per_100k_base'))} / "
        f"{_fmt(row.get('projected_pts_per_100k_optimistic'))}"
    )
    return (
        f"<b>{row['player_name']}</b> ({row.get('team', '')}) — {row.get('position_display', '')}<br>"
        f"Value: {_fmt(row['value'], '€')} | Points: {_fmt(row['points'])} | Avg: {_fmt(row['average'])}<br>"
        f"Pts/100k: {_fmt(row.get('points_per_100k'))} | Games: {row.get('matches_played', '—')} "
        f"(rate: {_fmt(row.get('participation_rate'))})<br>"
        f"Projected pess/base/opti: {proj_range}"
    )


def _build_scatter(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    sel_players: list[str],
    highlight_team_only: bool,
) -> go.Figure:
    fig = go.Figure()

    # Split into layers
    is_selected = df["player_name"].isin(sel_players)
    is_team = df["is_current_team"]

    bg_mask = ~is_team & ~is_selected
    team_mask = is_team & ~is_selected
    sel_mask = is_selected  # gold wins even if on team

    def _opacity(mask: pd.Series) -> list[float]:
        """If highlight_team_only, dim non-team non-selected rows further."""
        if not highlight_team_only:
            return [1.0] * mask.sum()
        return [1.0] * mask.sum()

    def _add_layer(
        sub: pd.DataFrame,
        size: int,
        border_color: str | None,
        border_width: float,
        opacity: float,
        show_labels: bool = False,
    ) -> None:
        if sub.empty:
            return
        for pos in POSITION_ORDER:
            grp = sub[sub["position_display"] == pos]
            if grp.empty:
                continue
            marker = dict(
                size=size,
                color=POSITION_COLOURS.get(pos, "#6b7280"),
                opacity=opacity,
                line=dict(
                    width=border_width,
                    color=border_color or "rgba(0,0,0,0)",
                ),
            )
            hover_texts = grp.apply(_hover_text, axis=1).tolist()
            trace = go.Scatter(
                x=grp[x_col],
                y=grp[y_col],
                mode="markers+text" if show_labels else "markers",
                marker=marker,
                text=grp["player_name"].tolist() if show_labels else None,
                textposition="top center",
                textfont=dict(
                    size=10, color=_SEL_BORDER_COLOUR if border_color == _SEL_BORDER_COLOUR else _TEAM_BORDER_COLOUR
                ),
                hovertext=hover_texts,
                hoverinfo="text",
                name=pos,
                legendgroup=pos,
                showlegend=False,  # legend handled by position traces below
            )
            fig.add_trace(trace)

    # Background layer: dim when highlight_team_only is on
    bg_opacity = 0.08 if highlight_team_only else 0.25
    _add_layer(df[bg_mask], size=7, border_color=None, border_width=0, opacity=bg_opacity)
    _add_layer(df[team_mask], size=11, border_color=_TEAM_BORDER_COLOUR, border_width=2.5, opacity=1.0)
    _add_layer(df[sel_mask], size=14, border_color=_SEL_BORDER_COLOUR, border_width=3, opacity=1.0, show_labels=True)

    # ── Position legend entries (dummy invisible traces) ──────────────────────
    for pos in POSITION_ORDER:
        if pos not in df["position_display"].values:
            continue
        fig.add_trace(
            go.Scatter(
                x=[None],
                y=[None],
                mode="markers",
                marker=dict(size=9, color=POSITION_COLOURS.get(pos, "#6b7280")),
                name=pos,
                legendgroup=pos,
                showlegend=True,
            )
        )

    # ── Highlight-type legend entries ─────────────────────────────────────────
    if is_team.any():
        fig.add_trace(
            go.Scatter(
                x=[None],
                y=[None],
                mode="markers",
                marker=dict(size=11, color="grey", line=dict(width=2.5, color=_TEAM_BORDER_COLOUR)),
                name="My squad",
                showlegend=True,
            )
        )
    if is_selected.any():
        fig.add_trace(
            go.Scatter(
                x=[None],
                y=[None],
                mode="markers",
                marker=dict(size=13, color="grey", line=dict(width=3, color=_SEL_BORDER_COLOUR)),
                name="Selected",
                showlegend=True,
            )
        )

    # ── Tertile guide lines ───────────────────────────────────────────────────
    _tertile_lines(fig, df[x_col], "x")
    _tertile_lines(fig, df[y_col], "y")

    fig.update_layout(
        height=560,
        margin=dict(l=20, r=180, t=30, b=20),
        xaxis_title=x_label,
        yaxis_title=y_label,
        legend=dict(
            orientation="v",
            x=1.02,
            y=1,
            xanchor="left",
            bgcolor="rgba(0,0,0,0)",
            borderwidth=0,
        ),
        hovermode="closest",
    )
    return fig


fig = _build_scatter(df, x_col, y_col, sel_players, highlight_team_only)
st.plotly_chart(fig, width="stretch")

# ── Table ─────────────────────────────────────────────────────────────────────

st.subheader("Player table")

# Show only columns that exist
available_cols = [c for c in _TABLE_COLUMNS if c in df.columns]
df_table = (
    df[available_cols].rename(columns=_TABLE_LABELS).sort_values("Pts/100k", ascending=False).reset_index(drop=True)
)

st.dataframe(df_table, width="stretch")
