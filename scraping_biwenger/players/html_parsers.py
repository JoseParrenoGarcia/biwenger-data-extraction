from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
import re
from typing import Optional

from scraping_biwenger.players.detail import (
    _normalize_status_category,
    _parse_float,
    _parse_int,
    _parse_money,
    _parse_percent,
)
from scraping_biwenger.players.matches import _to_date_iso, _to_int, NO_ROUNDS_TEXT_RE


@dataclass
class HtmlNode:
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    children: list["HtmlNode"] = field(default_factory=list)
    text_parts: list[str] = field(default_factory=list)

    def text(self) -> str:
        parts = list(self.text_parts)
        for child in self.children:
            parts.append(child.text())
        return re.sub(r"\s+", " ", " ".join(parts)).strip()

    def first_child_text(self, tag: str) -> str:
        for child in self.children:
            if child.tag == tag:
                return child.text()
        return ""

    def find_all(self, tag: str | None = None) -> list["HtmlNode"]:
        matches = []
        for child in self.children:
            if tag is None or child.tag == tag:
                matches.append(child)
            matches.extend(child.find_all(tag))
        return matches

    def first(self, tag: str) -> Optional["HtmlNode"]:
        matches = self.find_all(tag)
        return matches[0] if matches else None


class _MiniHtmlParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = HtmlNode("root")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = HtmlNode(tag.lower(), {key.lower(): value or "" for key, value in attrs})
        self.stack[-1].children.append(node)
        self.stack.append(node)

    def handle_endtag(self, tag):
        tag = tag.lower()
        for idx in range(len(self.stack) - 1, 0, -1):
            if self.stack[idx].tag == tag:
                del self.stack[idx:]
                return

    def handle_data(self, data):
        if data.strip():
            self.stack[-1].text_parts.append(data)


def parse_html_fragment(html: str) -> HtmlNode:
    parser = _MiniHtmlParser()
    parser.feed(html or "")
    return parser.root


def _class_contains(node: HtmlNode, value: str) -> bool:
    return value in (node.attrs.get("class") or "").split()


def _attr_equals(node: HtmlNode, attr: str, value: str) -> bool:
    return (node.attrs.get(attr) or "") == value


def _first_by_attr(root: HtmlNode, tag: str, attr: str, value: str) -> Optional[HtmlNode]:
    for node in root.find_all(tag):
        if _attr_equals(node, attr, value):
            return node
    return None


def _first_by_text(root: HtmlNode, tag: str, text: str) -> Optional[HtmlNode]:
    text_low = text.lower()
    for node in root.find_all(tag):
        if text_low in node.text().lower():
            return node
    return None


def parse_player_detail_html(html: str) -> dict:
    """
    Parse a curated player-detail HTML snippet into the raw player detail shape.

    This is intended for fixture tests and future pure parsing extraction. The
    live scraper still owns Playwright waits and component loading.
    """
    root = parse_html_fragment(html)
    header = root.first("player-detail-header") or root
    stats_root = root.first("player-detail-stats") or root

    name_node = header.first("h1")
    player_name = name_node.text() if name_node else ""
    for status_text in ("Fit", "Injured", "Doubtful", "Suspended"):
        player_name = re.sub(rf"\b{status_text}\b", "", player_name, flags=re.I).strip()

    team_link = header.first("a")
    position_node = header.first("player-position")
    status_node = header.first("player-status") or root.first("player-status")
    season_button = _first_by_attr(root, "button", "modalmenutitle", "Season")

    def stat_value(label: str) -> str:
        node = _first_by_text(stats_root, "div", label)
        return node.first_child_text("div") if node else ""

    def money_row(label: str) -> str:
        row = _first_by_text(stats_root, "tr", label)
        if not row:
            return ""
        cells = row.find_all("td")
        return cells[-1].text() if cells else ""

    purchases = _first_by_attr(stats_root, "div", "data-section", "Purchases")
    sales = _first_by_attr(stats_root, "div", "data-section", "Sales")
    usage = _first_by_attr(stats_root, "div", "data-section", "Usage")
    status_detail = None
    status = "fit"
    if status_node:
        status_detail = (
            status_node.attrs.get("aria-label")
            or status_node.attrs.get("title")
            or status_node.text()
            or None
        )
        status = _normalize_status_category(status_node.attrs.get("class", ""), status_detail or "")

    season = ""
    if season_button:
        season = re.sub(r"\s*season\s*$", "", season_button.text(), flags=re.I).strip()

    return {
        "player_name": player_name,
        "team": (team_link.attrs.get("title") if team_link else "") or "",
        "position": (
            position_node.attrs.get("title")
            or position_node.attrs.get("aria-label")
            or position_node.text()
            if position_node
            else ""
        ),
        "status": status,
        "status_detail": status_detail,
        "points": _parse_int(stat_value("Points")) or 0,
        "value": _parse_money(money_row("Value")) or 0,
        "min_value": _parse_money(money_row("Min")) or 0,
        "max_value": _parse_money(money_row("Max")) or 0,
        "matches_played": _parse_int(stat_value("Matches played")) or 0,
        "average": _parse_float(stat_value("Average")) or 0.0,
        "market_purchases_pct": _parse_percent(purchases.first_child_text("div") if purchases else "") or 0.0,
        "market_sales_pct": _parse_percent(sales.first_child_text("div") if sales else "") or 0.0,
        "market_usage_pct": _parse_percent(usage.first_child_text("div") if usage else "") or 0.0,
        "season": season,
    }


def parse_player_matches_html(html: str) -> list[dict]:
    root = parse_html_fragment(html)
    if NO_ROUNDS_TEXT_RE.search(root.text()):
        return []

    season_button = _first_by_attr(root, "button", "modalmenutitle", "Season")
    season_label = ""
    if season_button:
        season_label = re.sub(r"\s*season\s*$", "", season_button.text(), flags=re.I).strip()

    rows = []
    for tr in root.find_all("tr"):
        bar = next((node for node in tr.find_all("a") if _class_contains(node, "bar")), None)
        if not bar:
            continue
        round_link = next(
            (
                node
                for node in tr.find_all("a")
                if (node.attrs.get("title") or "").lower().startswith("round")
            ),
            None,
        )
        meta = next(
            (
                node
                for node in tr.find_all("meta")
                if node.attrs.get("itemprop") == "startDate"
            ),
            None,
        )
        events = [
            node.attrs["title"].strip()
            for node in tr.find_all("span")
            if node.attrs.get("title")
        ]
        round_label = round_link.text() if round_link else ""
        if not round_label:
            continue
        rows.append(
            {
                "season_label": season_label,
                "round_label": round_label,
                "match_date": _to_date_iso(meta.attrs.get("content", "")) if meta else None,
                "points": _to_int(bar.text()),
                "best_xi": _class_contains(bar, "star"),
                "events": " | ".join(events),
            }
        )

    unique = {}
    for row in rows:
        unique[(row["season_label"], row["round_label"])] = row
    return list(unique.values())
