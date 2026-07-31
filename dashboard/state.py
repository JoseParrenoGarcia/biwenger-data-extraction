"""
Shared Streamlit session-state helpers for dashboard pages.
"""

from __future__ import annotations

import streamlit as st

_SHARED_PLAYER_NAMES_KEY = "dashboard_shared_player_names"
_MARKET_TRENDS_WIDGET_KEY = "dashboard_market_trends_selected_labels"
_PLAYER_VALUE_WIDGET_KEY = "dashboard_player_value_selected_names"


def get_shared_player_names() -> list[str]:
    value = st.session_state.get(_SHARED_PLAYER_NAMES_KEY, [])
    return value if isinstance(value, list) else []


def set_shared_player_names(player_names: list[str]) -> None:
    st.session_state[_SHARED_PLAYER_NAMES_KEY] = player_names


def sync_market_trends_widget_to_shared(
    display_map: dict[str, str],
    slug_to_name: dict[str, str],
) -> None:
    selected_labels = st.session_state.get(_MARKET_TRENDS_WIDGET_KEY, [])
    selected_names = [
        slug_to_name[display_map[label]]
        for label in selected_labels
        if label in display_map and display_map[label] in slug_to_name
    ]
    set_shared_player_names(selected_names)


def seed_market_trends_widget_from_shared(
    all_options: list[str],
    display_map: dict[str, str],
    slug_to_name: dict[str, str],
) -> None:
    shared_names = set(get_shared_player_names())
    if _MARKET_TRENDS_WIDGET_KEY in st.session_state:
        return
    seeded_labels: list[str] = []
    for label in all_options:
        slug = display_map.get(label)
        if slug and slug_to_name.get(slug) in shared_names:
            seeded_labels.append(label)
    st.session_state[_MARKET_TRENDS_WIDGET_KEY] = seeded_labels


def sync_player_value_widget_to_shared() -> None:
    selected_names = st.session_state.get(_PLAYER_VALUE_WIDGET_KEY, [])
    set_shared_player_names(selected_names if isinstance(selected_names, list) else [])


def seed_player_value_widget_from_shared(valid_player_names: list[str]) -> None:
    if _PLAYER_VALUE_WIDGET_KEY in st.session_state:
        return
    shared_names = [name for name in get_shared_player_names() if name in valid_player_names]
    st.session_state[_PLAYER_VALUE_WIDGET_KEY] = shared_names
