"""Pulling readable text out of a message, for extraction only.

Nothing here goes anywhere near verification. By the time an extractor runs, the
signature has already been checked against the raw bytes; this module builds a
convenient *copy* to read, and that copy is never written back or re-hashed.
Keeping the two apart is the whole reason a mail library is safe to use at all.
"""

from __future__ import annotations

import email
import re
from dataclasses import dataclass
from email import policy
from html.parser import HTMLParser


@dataclass(frozen=True, slots=True)
class BodyPart:
    content_type: str
    text: str


def body_parts(raw: bytes) -> tuple[BodyPart, ...]:
    message = email.message_from_bytes(raw, policy=policy.default)
    parts: list[BodyPart] = []
    for part in message.walk():
        ctype = part.get_content_type()
        if ctype not in ("text/plain", "text/html"):
            continue
        try:
            payload = part.get_content()
        except Exception:  # malformed encoding shouldn't kill the whole read
            raw_payload = part.get_payload(decode=True)
            if raw_payload is None:
                continue
            payload = raw_payload.decode("utf-8", errors="replace")
        parts.append(BodyPart(ctype, payload))
    return tuple(parts)


def first_of(parts: tuple[BodyPart, ...], content_type: str) -> str | None:
    for part in parts:
        if part.content_type == content_type:
            return part.text
    return None


def header(raw: bytes, name: str) -> str | None:
    message = email.message_from_bytes(raw, policy=policy.default)
    value = message.get(name)
    return str(value) if value is not None else None


# -- tables ---------------------------------------------------------------

Row = list[str]
Table = list[Row]


class _TableCollector(HTMLParser):
    """Flattens every <table> into rows of cell text.

    Nested markup inside a cell is collapsed to its text, which is what we want:
    `<td><b>AAPL</b></td>` and `<td>AAPL</td>` should extract identically.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[Table] = []
        self._stack: list[Table] = []
        self._row: Row | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "table":
            self._stack.append([])
        elif tag == "tr" and self._stack:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(_squash(" ".join(self._cell)))
            self._cell = None
        elif tag == "tr" and self._row is not None and self._stack:
            if self._cell is not None:  # unclosed cell
                self._row.append(_squash(" ".join(self._cell)))
                self._cell = None
            self._stack[-1].append(self._row)
            self._row = None
        elif tag == "table" and self._stack:
            self.tables.append(self._stack.pop())

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def close(self) -> None:  # flush anything left open by sloppy markup
        super().close()
        while self._stack:
            self.tables.append(self._stack.pop())


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).replace("\xa0", " ").strip()


def tables(html: str) -> list[Table]:
    parser = _TableCollector()
    parser.feed(html)
    parser.close()
    return [t for t in parser.tables if t]


def text_from_html(html: str) -> str:
    """Crude tag strip, used only for regex sweeps over prose."""
    without_tags = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    without_tags = re.sub(r"<[^>]+>", " ", without_tags)
    return _squash(without_tags)
