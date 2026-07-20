from __future__ import annotations

import pandas as pd

from scraping_biwenger.current_team.scrape import (
    _match_id_from_url,
    _points_average_from_split_cell,
    _previous_season_points,
    _slug_from_url,
    _status_from_element,
    _to_float_generic,
    _to_int_generic,
    _to_int_money,
)
from scraping_biwenger.shared.html import HtmlNode, parse_html_fragment


def _class_contains(node: HtmlNode, value: str) -> bool:
    return value in (node.attrs.get("class") or "").split()


def _direct_cells(row: HtmlNode) -> list[HtmlNode]:
    return [child for child in row.children if child.tag in {"td", "th"}]


def _cell(cells: list[HtmlNode], index: int) -> HtmlNode:
    return cells[index] if len(cells) > index else HtmlNode("empty")


def _first_link(node: HtmlNode) -> HtmlNode | None:
    return node.first("a")


def _own_text(node: HtmlNode) -> str:
    return " ".join(part.strip() for part in node.text_parts if part.strip())


class _FixtureLocator:
    def __init__(self, nodes: list[HtmlNode]):
        self._nodes = nodes

    @property
    def first(self):
        return _FixtureLocator(self._nodes[:1])

    def count(self):
        return len(self._nodes)

    def inner_text(self):
        return self._nodes[0].text() if self._nodes else ""

    def get_attribute(self, attr: str):
        return self._nodes[0].attrs.get(attr) if self._nodes else None

    def locator(self, selector: str):
        if selector == "div.text-muted.small[title*='season points']":
            return _FixtureLocator(
                [
                    node
                    for node in self._nodes[0].find_all("div")
                    if _class_contains(node, "text-muted")
                    and _class_contains(node, "small")
                    and "season points" in (node.attrs.get("title") or "")
                ]
                if self._nodes
                else []
            )
        return _FixtureLocator([])


def _points_average_from_node(node: HtmlNode) -> tuple[int, float]:
    return _points_average_from_split_cell(_FixtureLocator([node]))


def _previous_points_from_node(node: HtmlNode) -> int | None:
    return _previous_season_points(_FixtureLocator([node]))


def _status_from_row(row: HtmlNode) -> str:
    class _RowLocator:
        def locator(self, selector: str):
            if selector != "player-status":
                return _FixtureLocator([])
            return _FixtureLocator(row.find_all("player-status"))

    return _status_from_element(_RowLocator())


def parse_current_team_table_html(html: str) -> pd.DataFrame:
    """
    Parse a curated current-team table fixture into the raw scrape dataframe.

    The live scraper still owns Playwright waits and browser locators. This
    parser is only for deterministic fixture coverage of the table contract.
    """
    root = parse_html_fragment(html)
    rows = []
    for tr in root.find_all("tr"):
        cells = _direct_cells(tr)
        if len(cells) < 13:
            continue

        position_cell = _cell(cells, 0)
        team_cell = _cell(cells, 1)
        player_cell = _cell(cells, 2)
        points_cell = _cell(cells, 3)
        market_value_cell = _cell(cells, 4)
        gp_cell = _cell(cells, 7)
        avg_cell = _cell(cells, 8)
        home_cell = _cell(cells, 9)
        away_cell = _cell(cells, 10)
        play_cell = _cell(cells, 11)
        opponent_cell = _cell(cells, 12)

        position_el = position_cell.first("player-position")
        team_link = _first_link(team_cell)
        player_link = _first_link(player_cell)
        opponent_link = _first_link(opponent_cell)
        player_url = player_link.attrs.get("href") if player_link else None
        next_match_url = opponent_link.attrs.get("href") if opponent_link else None
        home_points, home_average_points = _points_average_from_node(home_cell)
        away_points, away_average_points = _points_average_from_node(away_cell)
        form_container = tr.first("player-fitness")
        form_vals = [
            _to_int_generic(points_node.text())
            for points_node in (form_container.find_all("player-points") if form_container else [])
        ]
        form = (form_vals[:5] + [0] * 5)[:5]
        increment = market_value_cell.first("increment")
        mv_change_eur = 0
        if increment:
            mv_change_eur = _to_int_money(increment.text() or increment.attrs.get("aria-label", ""))
            if _class_contains(increment, "decrement"):
                mv_change_eur = -abs(mv_change_eur)

        rows.append(
            {
                "name": player_link.text() if player_link else "",
                "position_short": position_el.text() if position_el else None,
                "position": (
                    position_el.attrs.get("aria-label") or position_el.attrs.get("title") if position_el else None
                ),
                "team_name": team_link.attrs.get("title") if team_link else None,
                "player_slug": _slug_from_url(player_url),
                "player_url": player_url,
                "points": _to_int_generic(points_cell.text()),
                "previous_season_points": _previous_points_from_node(points_cell),
                "market_value": _to_int_money(_own_text(market_value_cell)),
                "mv_change_eur": mv_change_eur,
                "status": _status_from_row(tr),
                "games_played": _to_int_generic(gp_cell.text()),
                "average_points": _to_float_generic(avg_cell.text()),
                "home_points": home_points,
                "home_average_points": home_average_points,
                "away_points": away_points,
                "away_average_points": away_average_points,
                "next_fixture_location": play_cell.text() or None,
                "next_opponent": opponent_link.attrs.get("title") if opponent_link else None,
                "next_match_url": next_match_url,
                "next_match_id": _match_id_from_url(next_match_url),
                "form_t-1": form[0],
                "form_t-2": form[1],
                "form_t-3": form[2],
                "form_t-4": form[3],
                "form_t-5": form[4],
            }
        )

    return pd.DataFrame(rows)
