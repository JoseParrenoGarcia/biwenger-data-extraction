from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser


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

    def first(self, tag: str) -> "HtmlNode | None":
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
