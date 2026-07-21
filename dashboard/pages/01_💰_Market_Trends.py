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

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly import colors as pc

from dashboard.data import load_player_index, load_stats_history, load_value_history

st.set_page_config(page_title="Market Trends · Biwenger", layout="wide")

# ── Colour palette ────────────────────────────────────────────────────────────
# Colours are assigned by sorted slug position so the same player always gets
# the same colour regardless of selection order.

_PALETTE = pc.qualitative.Plotly  # 10 distinct, perceptually separated colours


def _colour_map(selected_slugs: list[str], all_slugs_sorted: list[str]) -> dict[str, str]:
    return {
        slug: _PALETTE[all_slugs_sorted.index(slug) % len(_PALETTE)]
        for slug in selected_slugs
        if slug in all_slugs_sorted
    }


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


# ── Shared chart styling ──────────────────────────────────────────────────────

_LAYOUT_BASE = dict(
    plot_bgcolor="white",
    paper_bgcolor="white",
    hovermode="x unified",
    margin=dict(l=10, r=10, t=50, b=40),
    font=dict(family="Inter, sans-serif", size=13),
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=1.02,
        xanchor="right",
        x=1,
        font=dict(size=12),
    ),
)

_XAXIS_STYLE = dict(showgrid=False, showline=True, linecolor="#e0e0e0", tickfont=dict(size=11))
_YAXIS_GRID = dict(showgrid=True, gridcolor="#f0f0f0", tickfont=dict(size=11))


# ── Chart builders ─────────────────────────────────────────────────────────────


def _build_value_chart(df: pd.DataFrame, colour_map: dict[str, str]) -> go.Figure:
    fig = go.Figure()
    for slug, grp in df.groupby("slug"):
        grp = grp.sort_values("date")
        label = grp["display_name"].iloc[0]
        fig.add_trace(
            go.Scatter(
                x=grp["date"],
                y=grp["market_value_eur"],
                mode="lines+markers",
                marker=dict(size=4, symbol="circle"),
                name=label,
                line=dict(color=colour_map.get(slug, "#888"), width=2),
                hovertemplate=(f"<b>{label}</b><br>%{{x|%d %b %Y}}<br>€%{{y:,.0f}}<extra></extra>"),
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


def _build_delta_chart(df: pd.DataFrame, colour_map: dict[str, str]) -> go.Figure:
    fig = go.Figure()
    for slug, grp in df.groupby("slug"):
        grp = grp.sort_values("date")
        label = grp["display_name"].iloc[0]
        fig.add_trace(
            go.Scatter(
                x=grp["date"],
                y=grp["value_change_1d"],
                mode="lines+markers",
                marker=dict(size=4, symbol="circle"),
                name=label,
                line=dict(color=colour_map.get(slug, "#888"), width=1.5),
                hovertemplate=(f"<b>{label}</b><br>%{{x|%d %b %Y}}<br>%{{y:+,.0f}}<extra></extra>"),
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


def _build_market_activity_chart(df: pd.DataFrame, colour_map: dict[str, str]) -> go.Figure:
    """Purchases % and sales % as separate lines per player.

    Each player contributes two traces: one solid (purchases) and one dashed (sales).
    """
    fig = go.Figure()
    for pname, grp in df.groupby("player_name"):
        grp = grp.sort_values("as_of_date")
        label = grp["display_name"].iloc[0]
        slug = grp["slug"].iloc[0] if grp["slug"].notna().any() else pname
        colour = colour_map.get(slug, colour_map.get(pname, "#888"))
        fig.add_trace(
            go.Scatter(
                x=grp["as_of_date"],
                y=grp["market_purchases_pct"],
                mode="lines+markers",
                marker=dict(size=5, symbol="circle"),
                name=f"{label} — buys",
                line=dict(color=colour, width=2, dash="solid"),
                hovertemplate=(f"<b>{label} — buys</b><br>%{{x|%d %b %Y}}<br>%{{y:.1f}}%<extra></extra>"),
            )
        )
        fig.add_trace(
            go.Scatter(
                x=grp["as_of_date"],
                y=grp["market_sales_pct"],
                mode="lines+markers",
                marker=dict(size=5, symbol="x"),
                name=f"{label} — sells",
                line=dict(color=colour, width=2, dash="dash"),
                hovertemplate=(f"<b>{label} — sells</b><br>%{{x|%d %b %Y}}<br>%{{y:.1f}}%<extra></extra>"),
            )
        )
    fig.update_layout(
        title=dict(text="Market Activity — Purchases vs. Sales %", font=dict(size=15, color="#333")),
        yaxis_title="% of market",
        yaxis_ticksuffix="%",
        height=360,
        **_LAYOUT_BASE,
    )
    fig.update_xaxes(**_XAXIS_STYLE)
    fig.update_yaxes(**_YAXIS_GRID, zeroline=False, rangemode="tozero")
    return fig


def _build_ratio_chart(df: pd.DataFrame, colour_map: dict[str, str]) -> go.Figure:
    """Purchase/sales ratio per player. Ratio > 1 means more buyers than sellers."""
    fig = go.Figure()
    for pname, grp in df.groupby("player_name"):
        grp = grp.sort_values("as_of_date")
        label = grp["display_name"].iloc[0]
        slug = grp["slug"].iloc[0] if grp["slug"].notna().any() else pname
        fig.add_trace(
            go.Scatter(
                x=grp["as_of_date"],
                y=grp["ratio_purchase_sales"],
                mode="lines+markers",
                marker=dict(size=5, symbol="circle"),
                name=label,
                line=dict(color=colour_map.get(slug, colour_map.get(pname, "#888")), width=2),
                hovertemplate=(f"<b>{label}</b><br>%{{x|%d %b %Y}}<br>ratio: %{{y:.2f}}<extra></extra>"),
            )
        )
    # Reference line: ratio = 1 (equal buys and sells)
    fig.add_hline(y=1, line_dash="dot", line_color="#aaaaaa", line_width=1)
    fig.update_layout(
        title=dict(text="Purchase / Sales Ratio  (>1 = more buyers than sellers)", font=dict(size=15, color="#333")),
        yaxis_title="Ratio",
        height=300,
        **_LAYOUT_BASE,
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

# ── Controls ──────────────────────────────────────────────────────────────────
with st.container(border=True):
    col_select, col_window = st.columns([5, 1])
    with col_select:
        selected_labels = st.multiselect(
            "Players",
            options=all_options,
            default=[],
            placeholder="Search for a player…",
        )
    with col_window:
        st.write("")  # vertical alignment nudge
        window = st.radio("Window", list(_WINDOWS.keys()), index=1, horizontal=True)

# ── Empty state ───────────────────────────────────────────────────────────────
if not selected_labels:
    st.info("Select one or more players above to see their market value trends.")
    st.stop()

# ── Phase 2 — fires when the user has selected players ───────────────────────
selected_slugs = tuple(display_map[lbl] for lbl in selected_labels)
selected_names = tuple(slug_to_name[s] for s in selected_slugs if s in slug_to_name)
today = pd.Timestamp.utcnow().normalize()
cutoff = _cutoff_date(window, today)
colour_map = _colour_map(list(selected_slugs), all_slugs_sorted)

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
    st.plotly_chart(_build_value_chart(df_val, colour_map), width="stretch")
    st.plotly_chart(_build_delta_chart(df_val, colour_map), width="stretch")

# ── Market activity charts ────────────────────────────────────────────────────
if not df_stats.empty:
    st.divider()
    st.caption("Market activity data comes from daily scraper snapshots — one point per scrape run.")
    st.plotly_chart(_build_market_activity_chart(df_stats, colour_map), width="stretch")
    st.plotly_chart(_build_ratio_chart(df_stats, colour_map), width="stretch")
elif not df_val.empty:
    st.divider()
    st.info("No market activity snapshots yet for the selected players / window.")
