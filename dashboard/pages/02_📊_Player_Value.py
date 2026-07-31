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
from plotly.subplots import make_subplots

from dashboard.data import load_all_player_stats, load_current_team
from dashboard.state import seed_player_value_widget_from_shared, sync_player_value_widget_to_shared
from dashboard.valuation import (
    POSITION_COLOURS,
    POSITION_ORDER,
    build_points_cohort,
    build_price_simulation_table,
    enrich_player_stats,
    mark_current_team,
    summarize_points_cohort,
)

st.set_page_config(layout="wide", page_title="Player Value Comparison")

# ── Constants ─────────────────────────────────────────────────────────────────

_TEAM_BORDER_COLOUR = "#111827"  # thick black → "I own this"
_HALO_OPACITY = 0.28  # selected-player bloom opacity

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

_SIM_DEFAULT_BID_DELTAS = [200_000, 500_000, 1_000_000]

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
seed_player_value_widget_from_shared(player_labels)
sel_players = st.multiselect(
    "Highlight players (gold ring)",
    player_labels,
    key="dashboard_player_value_selected_names",
    placeholder="Search for a player…",
    on_change=sync_player_value_widget_to_shared,
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

    def _add_halo_layer(sub: pd.DataFrame) -> None:
        """Large semi-transparent bloom in position colour — rendered before the crisp dot."""
        if sub.empty:
            return
        for pos in POSITION_ORDER:
            grp = sub[sub["position_display"] == pos]
            if grp.empty:
                continue
            fig.add_trace(
                go.Scatter(
                    x=grp[x_col],
                    y=grp[y_col],
                    mode="markers",
                    marker=dict(
                        size=18,
                        color=POSITION_COLOURS.get(pos, "#6b7280"),
                        opacity=_HALO_OPACITY,
                        line=dict(width=0),
                    ),
                    hoverinfo="skip",
                    showlegend=False,
                    legendgroup=pos,
                )
            )

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
                textfont=dict(size=10, color="#374151"),
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
    # Selected: halo bloom first, then crisp dot + label on top
    _add_halo_layer(df[sel_mask])
    _add_layer(
        df[sel_mask], size=11, border_color="rgba(255,255,255,0.9)", border_width=1.5, opacity=1.0, show_labels=True
    )

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
                marker=dict(size=18, color="rgba(107,114,128,0.28)", line=dict(width=0)),
                name="Selected (glow)",
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


def _fmt_money(v: float | int | None) -> str:
    if v is None or pd.isna(v):
        return "—"
    v = float(v)
    if abs(v) >= 1_000_000:
        return f"€{v / 1_000_000:.2f}M"
    return f"€{v:,.0f}"


def _fmt_delta(v: float | int | None) -> str:
    if v is None or pd.isna(v):
        return "—"
    v = float(v)
    sign = "+" if v >= 0 else "-"
    return f"{sign}{_fmt_money(abs(v))}"


def _fmt_signed_int(v: float | int | None) -> str:
    if v is None or pd.isna(v):
        return "—"
    return f"{int(round(float(v))):+d}"


def _classify_value_view(*, is_selected: bool, value_gap: float, eff_gap: float, pts_gap: float) -> str:
    if value_gap <= -300_000 and eff_gap >= -0.75 and abs(pts_gap) <= 8:
        return "Clear buy"
    if value_gap >= 800_000 and eff_gap <= 0.5:
        return "Too expensive"
    if is_selected:
        return "Similar"
    return "Similar"


def _value_view_label(tag: str) -> str:
    mapping = {
        "Clear buy": "🟢 Clear buy",
        "Similar": "🟡 Similar",
        "Too expensive": "🔴 Too expensive",
    }
    return mapping.get(tag, tag)


def _sim_player_option(row: pd.Series) -> str:
    return f"{row['player_name']} ({row['team']})"


def _build_cohort_efficiency_chart(cohort_df: pd.DataFrame) -> go.Figure:
    plot_df = cohort_df.sort_values(["points_per_100k", "points", "value"], ascending=[False, False, True]).copy()
    colors = np.where(plot_df["is_selected_player"], "#f59e0b", "#94a3b8")
    border_widths = np.where(plot_df["is_selected_player"], 2.5, 0)
    border_colors = np.where(plot_df["is_selected_player"], "#111827", "rgba(0,0,0,0)")

    fig = make_subplots(
        rows=1,
        cols=2,
        shared_yaxes=True,
        horizontal_spacing=0.08,
        column_widths=[0.62, 0.38],
        subplot_titles=("Points per 100k", "Total points"),
    )

    fig.add_trace(
        go.Bar(
            x=plot_df["points_per_100k"],
            y=plot_df["display_label"],
            orientation="h",
            marker=dict(color=colors, line=dict(color=border_colors, width=border_widths)),
            customdata=np.column_stack([plot_df["points"], plot_df["value"], plot_df["cohort_band"]]),
            text=plot_df["points_per_100k"].map(lambda v: f"{v:.2f}"),
            textposition="outside",
            cliponaxis=False,
            hovertemplate=(
                "<b>%{y}</b><br>"
                "Points/100k: %{x:.2f}<br>"
                "Points: %{customdata[0]:,.0f}<br>"
                "Value: €%{customdata[1]:,.0f}<br>"
                "Band: %{customdata[2]}<extra></extra>"
            ),
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Bar(
            x=plot_df["points"],
            y=plot_df["display_label"],
            orientation="h",
            marker=dict(color=colors, line=dict(color=border_colors, width=border_widths)),
            customdata=np.column_stack([plot_df["points_per_100k"], plot_df["value"], plot_df["cohort_band"]]),
            text=plot_df["points"].map(lambda v: f"{int(v)}"),
            textposition="outside",
            cliponaxis=False,
            hovertemplate=(
                "<b>%{y}</b><br>"
                "Total points: %{x:,.0f}<br>"
                "Points/100k: %{customdata[0]:.2f}<br>"
                "Value: €%{customdata[1]:,.0f}<br>"
                "Band: %{customdata[2]}<extra></extra>"
            ),
            showlegend=False,
        ),
        row=1,
        col=2,
    )
    fig.update_layout(
        height=max(360, 28 * len(plot_df)),
        margin=dict(l=10, r=10, t=30, b=10),
        plot_bgcolor="white",
        paper_bgcolor="white",
        showlegend=False,
    )
    fig.update_xaxes(showgrid=True, gridcolor="#eef2f7", zeroline=False, row=1, col=1, title_text="Points per 100k")
    fig.update_xaxes(showgrid=True, gridcolor="#eef2f7", zeroline=False, row=1, col=2, title_text="Total points")
    fig.update_yaxes(showgrid=False, autorange="reversed")
    return fig


def _build_simulation_heatmap(sim_df: pd.DataFrame, target_pp100k: float) -> go.Figure:
    value_cols = [c for c in sim_df.columns if c.endswith("pts/100k")]
    z = sim_df[value_cols].to_numpy(dtype=float)
    delta_vs_target = z - float(target_pp100k)
    text = np.vectorize(lambda x: "—" if pd.isna(x) else f"{x:.2f}")(z)

    fig = go.Figure(
        go.Heatmap(
            z=delta_vs_target,
            x=value_cols,
            y=sim_df["Scenario label"],
            text=text,
            texttemplate="%{text}",
            colorscale=[[0.0, "#b91c1c"], [0.5, "#f8fafc"], [1.0, "#15803d"]],
            zmid=0,
            colorbar=dict(title="Vs cohort median"),
            hovertemplate=(
                "Scenario: %{y}<br>"
                "Bid level: %{x}<br>"
                "Projected pts/100k: %{text}<br>"
                "Gap vs cohort median: %{z:.2f}<extra></extra>"
            ),
        )
    )
    fig.update_layout(
        height=320,
        margin=dict(l=10, r=10, t=30, b=10),
        plot_bgcolor="white",
        paper_bgcolor="white",
        xaxis_title="Bid scenario",
        yaxis_title="Points scenario",
    )
    return fig


fig = _build_scatter(df, x_col, y_col, sel_players, highlight_team_only)
st.plotly_chart(fig, width="stretch")

st.divider()
st.subheader("Fair Value Simulator")
st.caption("Pick one player, compare him to nearby same-position point totals, and stress-test how much efficiency you lose as the bid rises.")

sim_candidates = (
    df.sort_values(["points", "value"], ascending=[False, True])
    .dropna(subset=["player_name", "team", "position_display", "points", "value"])
    .copy()
)

if sim_candidates.empty:
    st.info("No players with enough data are available for simulation.")
else:
    sim_candidates["sim_option"] = sim_candidates.apply(_sim_player_option, axis=1)
    sim_option_to_index = dict(zip(sim_candidates["sim_option"], sim_candidates.index))

    default_sim_option = sim_candidates["sim_option"].iloc[0]
    if sel_players:
        matching = sim_candidates[sim_candidates["player_name"].isin(sel_players)]
        if not matching.empty:
            default_sim_option = matching["sim_option"].iloc[0]

    with st.container(border=True):
        ctrl_col1, ctrl_col2, ctrl_col3 = st.columns([3, 1, 2])
        selected_sim_option = ctrl_col1.selectbox(
            "Player",
            options=sim_candidates["sim_option"].tolist(),
            index=sim_candidates["sim_option"].tolist().index(default_sim_option),
        )
        neighbors_each_side = int(
            ctrl_col2.number_input("Players above / below", min_value=3, max_value=20, value=10, step=1)
        )
        ctrl_col3.caption("Cohort rule")
        ctrl_col3.write("Same position, nearest by total points from the full market dataset.")

        delta_col1, delta_col2, delta_col3 = st.columns(3)
        delta_inputs = [
            int(delta_col1.number_input("Bid delta 1 (€)", min_value=0, value=_SIM_DEFAULT_BID_DELTAS[0], step=50_000)),
            int(delta_col2.number_input("Bid delta 2 (€)", min_value=0, value=_SIM_DEFAULT_BID_DELTAS[1], step=50_000)),
            int(delta_col3.number_input("Bid delta 3 (€)", min_value=0, value=_SIM_DEFAULT_BID_DELTAS[2], step=50_000)),
        ]

    selected_index = sim_option_to_index[selected_sim_option]
    selected_market_row = df_all.loc[selected_index]
    selected_row, cohort_df = build_points_cohort(df_all, selected_index=selected_index, neighbors_each_side=neighbors_each_side)
    cohort_summary = summarize_points_cohort(selected_row, cohort_df)
    target_pp100k = cohort_summary["cohort_median_points_per_100k"]

    points_default_current = int(round(float(selected_row.get("points", 0))))
    points_default_base = int(round(float(selected_row.get("projected_points_base", points_default_current))))
    points_default_optimistic = int(round(float(selected_row.get("projected_points_optimistic", points_default_base))))

    with st.container(border=True):
        points_col1, points_col2, points_col3 = st.columns(3)
        point_scenarios = [
            ("Current points", float(points_col1.number_input("Points scenario 1", min_value=0, value=points_default_current, step=5))),
            ("Base projection", float(points_col2.number_input("Points scenario 2", min_value=0, value=points_default_base, step=5))),
            (
                "Upside projection",
                float(points_col3.number_input("Points scenario 3", min_value=0, value=points_default_optimistic, step=5)),
            ),
        ]

    sim_table = build_price_simulation_table(
        selected_row,
        bid_deltas=delta_inputs,
        point_scenarios=point_scenarios,
        cohort_target_points_per_100k=target_pp100k,
    )

    sim_table["Scenario label"] = sim_table.apply(
        lambda r: f"{r['Scenario']} ({int(round(float(r['Projected points'])))} pts)",
        axis=1,
    )
    sim_table["Market premium vs current"] = sim_table["Fair value @ cohort median"] - float(selected_row["value"])

    metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
    metric_col1.metric("Current value", _fmt_money(selected_row["value"]))
    metric_col2.metric("Current pts/100k", f"{selected_row['points_per_100k']:.2f}")
    metric_col3.metric("Cohort median pts/100k", f"{target_pp100k:.2f}" if pd.notna(target_pp100k) else "—")
    metric_col4.metric(
        "Fair value @ base projection",
        _fmt_money(cohort_summary["fair_value_projected_base"]),
        _fmt_delta(cohort_summary["fair_value_projected_base"] - float(selected_row["value"]))
        if pd.notna(cohort_summary["fair_value_projected_base"])
        else None,
    )

    viz_col1, viz_spacer, viz_col2 = st.columns([5, 1, 4])
    with viz_col1:
        st.caption("Selected player snapshot")
        st.write(
            f"**{selected_market_row['player_name']}** · {selected_market_row['team']} · {selected_market_row['position_display']}"
        )
        st.write(
            f"Scenario points: **Current {int(round(point_scenarios[0][1]))}** | "
            f"**Base {int(round(point_scenarios[1][1]))}** | "
            f"**Upside {int(round(point_scenarios[2][1]))}**"
        )
        st.plotly_chart(_build_cohort_efficiency_chart(cohort_df), width="stretch")
    with viz_spacer:
        st.write("")
    with viz_col2:
        st.caption("How to read it")
        st.write(
            "Green heatmap cells stay above the cohort's median efficiency. Once a bid column turns pale or red, "
            "you are paying above what similar same-position players usually justify on points-per-euro."
        )
        st.plotly_chart(_build_simulation_heatmap(sim_table, target_pp100k), width="stretch")

    comp_display = cohort_df[
        [
            "cohort_band",
            "player_name",
            "team",
            "points",
            "value",
            "points_per_100k",
            "points_gap",
            "value_gap",
        ]
    ].rename(
        columns={
            "cohort_band": "Band",
            "player_name": "Player",
            "team": "Team",
            "points": "Points",
            "value": "Value (€)",
            "points_per_100k": "Pts/100k",
            "points_gap": "Pts gap",
            "value_gap": "Value gap (€)",
        }
    )
    comp_display["Eff. gap"] = (
        cohort_df["points_per_100k"].to_numpy() - float(selected_row["points_per_100k"])
    ).round(2)
    comp_display["Value gap size (€)"] = cohort_df["value_gap"].abs().to_numpy()
    comp_display["Value view"] = [
        _classify_value_view(
            is_selected=bool(is_selected),
            value_gap=float(value_gap),
            eff_gap=float(eff_gap),
            pts_gap=float(pts_gap),
        )
        for is_selected, value_gap, eff_gap, pts_gap in zip(
            cohort_df["is_selected_player"].to_numpy(),
            cohort_df["value_gap"].to_numpy(),
            comp_display["Eff. gap"].to_numpy(),
            cohort_df["points_gap"].to_numpy(),
            strict=False,
        )
    ]
    comp_display["Value view"] = comp_display["Value view"].map(_value_view_label)
    comp_display["Pts gap"] = comp_display["Pts gap"].map(_fmt_signed_int)
    comp_display["Value gap (€)"] = cohort_df["value_gap"].map(_fmt_delta)
    comp_display = comp_display[
        [
            "Band",
            "Player",
            "Team",
            "Points",
            "Pts/100k",
            "Eff. gap",
            "Value gap (€)",
            "Value gap size (€)",
            "Value view",
            "Pts gap",
        ]
    ]

    st.caption("Nearest same-position players by total points")
    comp_table_height = min(max(36 * len(comp_display) + 44, 240), 780)
    st.dataframe(
        comp_display,
        width="stretch",
        height=comp_table_height,
        hide_index=True,
        column_config={
            "Points": st.column_config.ProgressColumn(
                "Points",
                format="%d",
                min_value=int(comp_display["Points"].min()),
                max_value=int(comp_display["Points"].max()),
            ),
            "Pts/100k": st.column_config.ProgressColumn(
                "Pts/100k",
                format="%.2f",
                min_value=float(comp_display["Pts/100k"].min()),
                max_value=float(comp_display["Pts/100k"].max()),
            ),
            "Eff. gap": st.column_config.NumberColumn(format="%+.2f"),
            "Value gap size (€)": st.column_config.ProgressColumn(
                "Value gap size (€)",
                format="€%d",
                min_value=0,
                max_value=float(comp_display["Value gap size (€)"].max()),
            ),
        },
    )

    fair_value_table = sim_table.copy()
    st.caption("Scenario table")
    st.dataframe(
        fair_value_table,
        width="stretch",
        hide_index=True,
        column_config={
            "Projected points": st.column_config.NumberColumn(format="%.0f"),
            "Fair value @ cohort median": st.column_config.NumberColumn(format="€%d"),
            "Market premium vs current": st.column_config.NumberColumn(format="€%d"),
            **{
                col: st.column_config.NumberColumn(format="%.2f")
                for col in fair_value_table.columns
                if col.endswith("pts/100k")
            },
        },
    )

# ── Table ─────────────────────────────────────────────────────────────────────

st.subheader("Player table")

# Quick-filter: reuse position/team/player selections already set above
df_table_src = df.copy()
if highlight_team_only:
    df_table_src = df_table_src[df_table_src["is_current_team"]]
elif sel_players:
    df_table_src = df_table_src[df_table_src["is_current_team"] | df_table_src["player_name"].isin(sel_players)]

available_cols = [c for c in _TABLE_COLUMNS if c in df_table_src.columns]
df_table = (
    df_table_src[available_cols]
    .rename(columns=_TABLE_LABELS)
    .sort_values("Pts/100k", ascending=False)
    .reset_index(drop=True)
)

st.dataframe(df_table, width="stretch")
