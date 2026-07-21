"""
Market value trends page.

Player multiselect + time window → two Plotly charts:
  1. Market value over time (absolute).
  2. Value change vs. previous recorded observation.

Load strategy (two phases):
  Phase 1 — cheap: fetch only (slug, player_name, team, date) to populate
    the player multiselect.  Paginates but only transfers 4 columns.
  Phase 2 — on demand: once the user selects players, fetch full value rows
    for only those slugs, filtered server-side by date window.

Run via:
    streamlit run dashboard/app.py
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly import colors as pc

from dashboard.queries import fetch_value_history_for_slugs, fetch_value_player_index

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


# ── Phase 1: player index (cheap, cached) ────────────────────────────────────


@st.cache_data(ttl=300)
def _load_player_index() -> pd.DataFrame:
    """Slug + display label only — used to populate the multiselect."""
    df = fetch_value_player_index()
    if df.empty:
        return df
    df["display_name"] = df.apply(
        lambda r: (
            f"{r['player_name']} ({r['team']})"
            if pd.notna(r.get("player_name")) and pd.notna(r.get("team"))
            else (r.get("player_name") or r.get("slug", "Unknown"))
        ),
        axis=1,
    )
    return df


def _player_options(index_df: pd.DataFrame) -> tuple[list[str], dict[str, str], list[str]]:
    """Return (sorted labels, label→slug map, sorted slug list)."""
    mapping: dict[str, str] = dict(zip(index_df["display_name"], index_df["slug"]))
    all_slugs_sorted = sorted(index_df["slug"].tolist())
    return sorted(mapping.keys()), mapping, all_slugs_sorted


# ── Phase 2: value history (on-demand, per-slug, cached) ─────────────────────


@st.cache_data(ttl=300)
def _load_selected_history(slugs: tuple[str, ...], cutoff: str | None) -> pd.DataFrame:
    """Fetch value rows for the chosen slugs, filtered server-side by date."""
    df = fetch_value_history_for_slugs(list(slugs), cutoff_date=cutoff)
    if df.empty:
        return df
    df["display_name"] = df.apply(
        lambda r: (
            f"{r['player_name']} ({r['team']})"
            if pd.notna(r.get("player_name")) and pd.notna(r.get("team"))
            else (r.get("player_name") or r.get("slug", "Unknown"))
        ),
        axis=1,
    )
    return df


# ── Enrichment ────────────────────────────────────────────────────────────────


def _with_delta(df: pd.DataFrame) -> pd.DataFrame:
    """Add value_change_1d: change vs. the previous recorded observation per slug."""
    df = df.sort_values(["slug", "date"]).copy()
    df["value_change_1d"] = df.groupby("slug")["market_value_eur"].diff()
    return df


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


# ── Chart builders ────────────────────────────────────────────────────────────


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
    fig.update_yaxes(
        **_YAXIS_GRID,
        zeroline=True,
        zerolinecolor="#cccccc",
        zerolinewidth=1,
    )
    return fig


# ── Page layout ───────────────────────────────────────────────────────────────

st.title("💰 Market Trends")
st.caption("Compare player value trajectories to support buy · hold · sell decisions.")

# Phase 1 — always runs, cheap.
with st.spinner("Loading player list…"):
    index_df = _load_player_index()

if index_df.empty:
    st.warning("No market value data available yet.")
    st.stop()

all_options, display_map, all_slugs_sorted = _player_options(index_df)

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

# ── Phase 2 — only fires when the user has selected players ──────────────────
selected_slugs = tuple(display_map[lbl] for lbl in selected_labels)
today = pd.Timestamp.utcnow().normalize()
cutoff = _cutoff_date(window, today)

with st.spinner("Loading value history…"):
    df_sel = _load_selected_history(selected_slugs, cutoff)

df_sel = _with_delta(df_sel)

# Warn for any player whose slug returned no rows.
present_slugs = set(df_sel["slug"].unique())
missing = [lbl for lbl, slug in zip(selected_labels, selected_slugs) if slug not in present_slugs]
if missing:
    st.warning(f"No data in the **{window}** window for: {', '.join(missing)}")

if df_sel.empty:
    st.stop()

colour_map = _colour_map(list(selected_slugs), all_slugs_sorted)

# ── Charts ────────────────────────────────────────────────────────────────────
st.plotly_chart(_build_value_chart(df_sel, colour_map), width="stretch")
st.plotly_chart(_build_delta_chart(df_sel, colour_map), width="stretch")
