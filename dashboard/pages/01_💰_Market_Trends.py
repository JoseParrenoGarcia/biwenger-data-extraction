"""
Market value trends page.

Player multiselect + time window → charts:
  1. Market value over time (absolute).
  2. Daily value change vs. previous observation.
  3. Market purchases % and sales % over time (from daily stats snapshots).
  4. Purchase/sales ratio over time.

Load strategy (two phases):
  Phase 1 — cheap: fetch only (slug, player_name, team) for the dropdown.
  Phase 2 — on demand: fetch value history and stats history for selected slugs,
    both filtered server-side by date window.

Run via:
    streamlit run dashboard/app.py
"""

# The path bootstrap below must run before importing the local dashboard package.
# ruff: noqa: E402

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.colors import qualitative

from dashboard.data import (
    load_latest_market_stats,
    load_player_index,
    load_stats_history,
    load_value_history,
)
from dashboard.state import (
    seed_market_trends_widget_from_shared,
    sync_market_trends_widget_to_shared,
)

st.set_page_config(page_title="Market Trends · Biwenger", layout="wide")

# ── Window helpers ────────────────────────────────────────────────────────────

_WINDOWS = {"7d": 7, "30d": 30, "All": None}


def _cutoff_date(window: str, reference: pd.Timestamp) -> str | None:
    days = _WINDOWS.get(window)
    if days is None:
        return None
    return (reference - pd.Timedelta(days=days)).strftime("%Y-%m-%d")


def _player_options(index_df: pd.DataFrame) -> tuple[list[str], dict[str, str], list[str], dict[str, str]]:
    """Return (sorted labels, label→slug map, sorted slug list, slug→player_name map)."""
    mapping: dict[str, str] = dict(zip(index_df["display_name"], index_df["slug"]))
    slug_to_name: dict[str, str] = dict(zip(index_df["slug"], index_df["player_name"]))
    all_slugs_sorted = sorted(index_df["slug"].tolist())
    return sorted(mapping.keys()), mapping, all_slugs_sorted, slug_to_name


# ── Number formatting ──────────────────────────────────────────────────────


def _fmt_k(v: float) -> str:
    """Format a signed euro value as +140k / -20k / +1.4M."""
    if v != v:  # NaN
        return "—"
    sign = "+" if v >= 0 else "-"
    abs_v = abs(v)
    if abs_v >= 1_000_000:
        return f"{sign}{abs_v / 1_000_000:.1f}M"
    if abs_v >= 1_000:
        return f"{sign}{abs_v / 1_000:.0f}k"
    return f"{sign}{abs_v:.0f}"


# ── Shared chart styling ──────────────────────────────────────────────────────

_LEGEND_V = dict(
    orientation="v",
    yanchor="middle",
    y=0.5,
    xanchor="left",
    x=1.02,
    font=dict(size=11),
    bgcolor="rgba(0,0,0,0)",
    borderwidth=0,
)

_LAYOUT_BASE = dict(
    plot_bgcolor="white",
    paper_bgcolor="white",
    hovermode="x unified",
    margin=dict(l=10, r=160, t=50, b=40),
    font=dict(family="Inter, sans-serif", size=13),
    legend=_LEGEND_V,
)

_LAYOUT_LEGEND_V = _LEGEND_V  # alias kept for stats chart builders

_XAXIS_STYLE = dict(showgrid=False, showline=True, linecolor="#e0e0e0", tickfont=dict(size=11))
_YAXIS_GRID = dict(showgrid=True, gridcolor="#f0f0f0", tickfont=dict(size=11))


def _player_colours(player_slugs: tuple[str, ...], slug_to_name: dict[str, str]) -> dict[str, str]:
    """Assign each selected player one colour for every chart on this page."""
    palette = qualitative.Plotly
    colours: dict[str, str] = {}
    for index, slug in enumerate(player_slugs):
        colour = palette[index % len(palette)]
        colours[slug] = colour
        if slug in slug_to_name:
            colours[slug_to_name[slug]] = colour
    return colours


# ── Chart builders ─────────────────────────────────────────────────────────────

_DIMMED_OPACITY = 0.15


def _trace_style(key: str, highlighted: str | None, base_width: float, base_marker: float) -> dict:
    """Return opacity/width/marker-size for a trace, dimming everyone but `highlighted`."""
    if highlighted is None:
        return dict(opacity=1.0, width=base_width, marker=base_marker)
    if key == highlighted:
        return dict(opacity=1.0, width=base_width + 1.5, marker=base_marker + 2)
    return dict(opacity=_DIMMED_OPACITY, width=base_width, marker=base_marker)


def _build_value_chart(df: pd.DataFrame, player_colours: dict[str, str], highlighted: str | None = None) -> go.Figure:
    fig = go.Figure()
    for slug, grp in df.groupby("slug"):
        grp = grp.sort_values("date")
        label = grp["display_name"].iloc[0]
        style = _trace_style(slug, highlighted, base_width=2, base_marker=4)
        fig.add_trace(
            go.Scatter(
                x=grp["date"],
                y=grp["market_value_eur"],
                mode="lines+markers",
                marker=dict(size=style["marker"], symbol="circle", color=player_colours[slug]),
                name=label,
                line=dict(width=style["width"], color=player_colours[slug]),
                opacity=style["opacity"],
                hovertemplate=(f"<b>{label}</b><br>€%{{y:,.0f}}<extra></extra>"),
            )
        )
    fig.update_layout(
        title=dict(text="Market Value", font=dict(size=15, color="#333")),
        yaxis_title="Value (€)",
        yaxis_tickprefix="€",
        yaxis_tickformat=",.0f",
        height=420,
        **_LAYOUT_BASE,
    )
    fig.update_xaxes(**_XAXIS_STYLE)
    fig.update_yaxes(**_YAXIS_GRID, zeroline=False)
    return fig


def _build_delta_chart(df: pd.DataFrame, player_colours: dict[str, str], highlighted: str | None = None) -> go.Figure:
    fig = go.Figure()
    for slug, grp in df.groupby("slug"):
        grp = grp.sort_values("date")
        label = grp["display_name"].iloc[0]
        style = _trace_style(slug, highlighted, base_width=1.5, base_marker=4)
        fig.add_trace(
            go.Scatter(
                x=grp["date"],
                y=grp["value_change_1d"],
                mode="lines+markers",
                marker=dict(size=style["marker"], symbol="circle", color=player_colours[slug]),
                name=label,
                line=dict(width=style["width"], color=player_colours[slug]),
                opacity=style["opacity"],
                customdata=grp["value_change_1d"].apply(_fmt_k),
                hovertemplate=(f"<b>{label}</b><br>%{{customdata}}<extra></extra>"),
            )
        )
    fig.add_hline(y=0, line_dash="dot", line_color="#aaaaaa", line_width=1)
    fig.update_layout(
        title=dict(text="Value Change (vs. previous observation)", font=dict(size=15, color="#333")),
        yaxis_title="Change (€)",
        yaxis_tickprefix="€",
        yaxis_tickformat=",.0f",
        height=340,
        **_LAYOUT_BASE,
    )
    fig.update_xaxes(**_XAXIS_STYLE)
    fig.update_yaxes(**_YAXIS_GRID, zeroline=True, zerolinecolor="#cccccc", zerolinewidth=1)
    return fig


def _build_market_activity_chart(
    df: pd.DataFrame, player_colours: dict[str, str], highlighted: str | None = None
) -> go.Figure:
    """Purchases % — one line per player."""
    fig = go.Figure()
    for pname, grp in df.groupby("player_name"):
        grp = grp.sort_values("as_of_date")
        label = grp["display_name"].iloc[0]
        style = _trace_style(pname, highlighted, base_width=2, base_marker=5)
        fig.add_trace(
            go.Scatter(
                x=grp["as_of_date"],
                y=grp["market_purchases_pct"],
                mode="lines+markers",
                marker=dict(size=style["marker"], symbol="circle", color=player_colours[pname]),
                name=label,
                line=dict(width=style["width"], dash="solid", color=player_colours[pname]),
                opacity=style["opacity"],
                hovertemplate=(f"<b>{label}</b><br>%{{y:.1f}}%<extra></extra>"),
            )
        )
    layout = {**_LAYOUT_BASE, "legend": _LAYOUT_LEGEND_V, "margin": dict(l=10, r=160, t=50, b=40)}
    fig.update_layout(
        title=dict(text="Market Purchases %", font=dict(size=15, color="#333")),
        yaxis_title="% of market",
        yaxis_ticksuffix="%",
        height=320,
        **layout,
    )
    fig.update_xaxes(**_XAXIS_STYLE)
    fig.update_yaxes(**_YAXIS_GRID, zeroline=False, rangemode="tozero")
    return fig


def _build_ratio_chart(df: pd.DataFrame, player_colours: dict[str, str], highlighted: str | None = None) -> go.Figure:
    """Purchase/sales ratio per player. Ratio > 1 means more buyers than sellers.

    On days with zero sales the true ratio is undefined; we estimate it from
    today's purchases over the last known non-zero sales and mark those points
    with a hollow marker so they are distinguishable from real observations.
    """
    fig = go.Figure()
    for pname, grp in df.groupby("player_name"):
        grp = grp.sort_values("as_of_date").reset_index(drop=True)
        label = grp["display_name"].iloc[0]
        style = _trace_style(pname, highlighted, base_width=2, base_marker=5)
        ratio, imputed, hover_text = _imputed_ratio_series(grp)
        symbols = ["circle-open" if imp else "circle" for imp in imputed]
        fig.add_trace(
            go.Scatter(
                x=grp["as_of_date"],
                y=ratio,
                mode="lines+markers",
                marker=dict(size=style["marker"], symbol=symbols, color=player_colours[pname]),
                name=label,
                line=dict(width=style["width"], color=player_colours[pname]),
                opacity=style["opacity"],
                text=hover_text,
                hovertemplate=(f"<b>{label}</b><br>%{{text}}<extra></extra>"),
            )
        )
    fig.add_hline(y=1, line_dash="dot", line_color="#aaaaaa", line_width=1)
    layout = {**_LAYOUT_BASE, "legend": _LAYOUT_LEGEND_V, "margin": dict(l=10, r=160, t=50, b=40)}
    fig.update_layout(
        title=dict(text="Purchase / Sales Ratio  (>1 = more buyers than sellers)", font=dict(size=15, color="#333")),
        yaxis_title="Ratio",
        height=300,
        **layout,
    )
    fig.update_xaxes(**_XAXIS_STYLE)
    fig.update_yaxes(**_YAXIS_GRID, zeroline=False, rangemode="tozero")
    return fig


# ── Page layout ───────────────────────────────────────────────────────────────

st.title("💰 Market Trends")
st.caption("Compare player value trajectories to support buy · hold · sell decisions.")

# Phase 1 — always runs, cheap.
with st.spinner("Loading player list…"):
    index_df = load_player_index()

if index_df.empty:
    st.warning("No market value data available yet.")
    st.stop()

all_options, display_map, all_slugs_sorted, slug_to_name = _player_options(index_df)
seed_market_trends_widget_from_shared(all_options, display_map, slug_to_name)

# ── Controls ──────────────────────────────────────────────────────────────────
with st.container(border=True):
    col_select, col_window = st.columns([5, 1])
    with col_select:
        selected_labels = st.multiselect(
            "Players",
            options=all_options,
            key="dashboard_market_trends_selected_labels",
            placeholder="Search for a player…",
            on_change=sync_market_trends_widget_to_shared,
            kwargs={"display_map": display_map, "slug_to_name": slug_to_name},
        )
    with col_window:
        st.write("")  # vertical alignment nudge
        window = st.radio("Window", list(_WINDOWS.keys()), index=1, horizontal=True)

    if selected_labels:
        highlight_label = st.pills(
            "Highlight (dims everyone else, on every chart below)",
            options=["All"] + selected_labels,
            default="All",
            key="dashboard_market_trends_highlight",
        )
    else:
        highlight_label = "All"

highlighted_slug = display_map.get(highlight_label) if highlight_label != "All" else None
highlighted_name = slug_to_name.get(highlighted_slug) if highlighted_slug else None

# ── Similar players (by purchase/sales ratio) ─────────────────────────────────
with st.expander("🔍 Find players with a similar purchase/sales ratio"):
    latest_stats = load_latest_market_stats()
    if latest_stats.empty:
        st.info("No stats snapshots available yet.")
    else:
        default_anchor_index = all_options.index(selected_labels[0]) if selected_labels else 0
        anchor_label = st.selectbox(
            "Anchor player",
            options=all_options,
            index=default_anchor_index,
            key="dashboard_market_trends_similar_anchor",
        )
        col_tol, col_n = st.columns(2)
        with col_tol:
            tolerance_pct = st.slider("Value tolerance (±%)", min_value=5, max_value=50, value=20, step=1)
        with col_n:
            top_n = st.slider("Number of peers", min_value=5, max_value=25, value=10, step=1)

        anchor_slug = display_map[anchor_label]
        anchor_rows = latest_stats[latest_stats["slug"] == anchor_slug]
        if anchor_rows.empty or pd.isna(anchor_rows["ratio_purchase_sales"].iloc[0]):
            st.warning(f"No usable ratio data for **{anchor_label}** yet.")
        else:
            anchor_value = anchor_rows["value"].iloc[0]
            anchor_ratio = anchor_rows["ratio_purchase_sales"].iloc[0]
            lower = anchor_value * (1 - tolerance_pct / 100)
            upper = anchor_value * (1 + tolerance_pct / 100)
            candidates = latest_stats[
                (latest_stats["slug"] != anchor_slug)
                & latest_stats["ratio_purchase_sales"].notna()
                & latest_stats["value"].between(lower, upper)
            ].copy()
            candidates["ratio_diff"] = (candidates["ratio_purchase_sales"] - anchor_ratio).abs()
            peers = candidates.sort_values("ratio_diff").head(top_n)

            if peers.empty:
                st.info(f"No peers found within ±{tolerance_pct}% of {anchor_label}'s value.")
            else:
                st.caption(
                    f"Anchor: **{anchor_label}** — value €{anchor_value:,.0f}, "
                    f"ratio {anchor_ratio:.2f}. Peers within ±{tolerance_pct}% value, "
                    "ranked by closest ratio."
                )
                st.dataframe(
                    peers[
                        [
                            "display_name",
                            "team",
                            "value",
                            "ratio_purchase_sales",
                            "market_purchases_pct",
                            "market_sales_pct",
                        ]
                    ].rename(
                        columns={
                            "display_name": "Player",
                            "team": "Team",
                            "value": "Value (€)",
                            "ratio_purchase_sales": "Ratio",
                            "market_purchases_pct": "Purchases %",
                            "market_sales_pct": "Sales %",
                        }
                    ),
                    width="stretch",
                    hide_index=True,
                )

                peer_labels = [
                    lbl
                    for lbl, slug in display_map.items()
                    if slug in set(peers["slug"]) and lbl not in selected_labels
                ]

                def _add_peers_to_comparison(labels: list[str]) -> None:
                    current = st.session_state.get("dashboard_market_trends_selected_labels", [])
                    st.session_state["dashboard_market_trends_selected_labels"] = list(
                        dict.fromkeys([*current, *labels])
                    )
                    sync_market_trends_widget_to_shared(display_map=display_map, slug_to_name=slug_to_name)

                st.button(
                    f"Add these {len(peer_labels)} peers to the comparison charts"
                    if peer_labels
                    else "All peers already selected",
                    disabled=not peer_labels,
                    on_click=_add_peers_to_comparison,
                    args=(peer_labels,),
                )

# ── Empty state ───────────────────────────────────────────────────────────────
if not selected_labels:
    st.info("Select one or more players above to see their market value trends.")
    st.stop()

# ── Phase 2 — fires when the user has selected players ───────────────────────
selected_slugs = tuple(display_map[lbl] for lbl in selected_labels)
selected_names = tuple(slug_to_name[s] for s in selected_slugs if s in slug_to_name)
player_colours = _player_colours(selected_slugs, slug_to_name)
today = pd.Timestamp.utcnow().normalize()
cutoff = _cutoff_date(window, today)
with st.spinner("Loading value history…"):
    df_val = load_value_history(selected_slugs, cutoff)

with st.spinner("Loading market stats…"):
    df_stats = load_stats_history(selected_names, cutoff)

# Warn for any player with no value rows in the chosen window.
present_val = set(df_val["slug"].unique()) if not df_val.empty else set()
missing = [lbl for lbl, slug in zip(selected_labels, selected_slugs) if slug not in present_val]
if missing:
    st.warning(f"No value data in the **{window}** window for: {', '.join(missing)}")

# ── Value charts ──────────────────────────────────────────────────────────────
if not df_val.empty:
    st.plotly_chart(_build_value_chart(df_val, player_colours, highlighted_slug), width="stretch")
    st.plotly_chart(_build_delta_chart(df_val, player_colours, highlighted_slug), width="stretch")

# ── Market activity charts ────────────────────────────────────────────────────
if not df_stats.empty:
    st.divider()
    st.caption("Market activity data comes from daily scraper snapshots — one point per scrape run.")
    st.plotly_chart(_build_market_activity_chart(df_stats, player_colours, highlighted_name), width="stretch")
    st.plotly_chart(_build_ratio_chart(df_stats, player_colours, highlighted_name), width="stretch")
    st.caption(
        "Hollow dots on the ratio chart are estimates for days with 0% sales "
        "(today's purchases ÷ last known non-zero sales)."
    )
elif not df_val.empty:
    st.divider()
    st.info("No market activity snapshots yet for the selected players / window.")
