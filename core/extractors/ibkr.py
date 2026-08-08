"""Interactive Brokers.

Trade confirmations first, deliberately. Statements from most brokers are a
notification — "your statement is ready, log in" — with no numbers in the body,
and a signature over that sentence proves nothing about a track record. A trade
confirmation carries the fill in the body, so the institution's key is signing
over the actual figures.

The statement extractor below exists because trades alone cannot produce a TWR:
you need a NAV series and the external flows between them. IBKR will embed both
in the mail body when HTML delivery is switched on, which is a setting the
manager has to turn on — and if they haven't, the flows arrive as CSV and the
tier drops to self_reported. That is the ladder working, not a bug.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Sequence

from core.extraction.base import ExtractedFact, ExtractionResult, registry
from core.extractors.mime import Table, body_parts, first_of, tables, text_from_html
from core.extractors.numbers import (
    normalize_header,
    parse_date,
    parse_decimal,
    to_minor,
)
from core.types import DocType, FactKind, Institution

INSTITUTION = Institution(
    id="ibkr",
    name="Interactive Brokers",
    domains=("interactivebrokers.com", "ibkr.com"),
    doc_types=(DocType.TRADE_CONFIRMATION, DocType.STATEMENT),
)

_ACCOUNT_RE = re.compile(r"\bU\d{7,9}\b")
_BASE_CCY_RE = re.compile(r"base\s+currency\s*[:\-]?\s*([A-Z]{3})", re.I)

# Bounded date shapes. An open-ended `(.+?)` here is how you end up dating a
# statement by the settle date of a deposit that happened to appear further
# down the page — which is exactly what the first version of this did.
_DATE_TOKEN = (
    r"(?:\d{4}-\d{2}-\d{2}"
    r"|[A-Z][a-z]{2,8}\s+\d{1,2},\s*\d{4}"
    r"|\d{1,2}\s+[A-Z][a-z]{2,8}\s+\d{4}"
    r"|\d{1,2}/\d{1,2}/\d{4})"
)
_PERIOD_RE = re.compile(
    rf"period\s*[:\-]?\s*({_DATE_TOKEN})\s*(?:-|–|—|to)\s*({_DATE_TOKEN})", re.I
)
_STATEMENT_DATE_RE = re.compile(rf"statement\s+date\s*[:\-]?\s*({_DATE_TOKEN})", re.I)

# Column headers we know how to read, and everything each is called in the wild.
_ALIASES: dict[str, set[str]] = {
    "symbol": {"symbol", "instrument", "underlying", "description"},
    "when": {"date/time", "date", "trade date", "date & time", "settle date"},
    "quantity": {"quantity", "qty", "shares"},
    "price": {"t. price", "t.price", "trade price", "price", "exec price"},
    "proceeds": {"proceeds", "gross amount", "amount", "net amount"},
    "fee": {"comm/fee", "comm/tax", "commission", "comm", "commission/fee", "fees"},
    "currency": {"currency", "ccy", "curr"},
}


def _column_map(header_row: Sequence[str]) -> dict[str, int]:
    found: dict[str, int] = {}
    for idx, cell in enumerate(header_row):
        name = normalize_header(cell)
        for field, aliases in _ALIASES.items():
            if name in aliases and field not in found:
                found[field] = idx
    return found


def _find_table(
    all_tables: list[Table], *required: str, exclude: tuple[str, ...] = ()
) -> tuple[Table, dict[str, int]] | None:
    """Locate a table by what its header row promises, not by position.

    Position-based parsing breaks the first time the institution adds a column,
    and it breaks silently, which is the worst way for a parser to break.

    `exclude` is how trades and flows are told apart. Both have a date and an
    amount; only trades have a quantity. Discriminating on a column that must be
    absent is sturdier than guessing from the values in the rows.
    """
    for table in all_tables:
        for row in table[:3]:  # header is at or near the top
            columns = _column_map(row)
            if all(name in columns for name in required) and not any(
                name in columns for name in exclude
            ):
                header_index = table.index(row)
                return table[header_index + 1 :], columns
    return None


def _cell(row: Sequence[str], columns: dict[str, int], name: str) -> str | None:
    idx = columns.get(name)
    if idx is None or idx >= len(row):
        return None
    value = row[idx].strip()
    return value or None


def _is_noise(row: Sequence[str], columns: dict[str, int]) -> bool:
    """Subtotals, section breaks and blank spacers all look like data rows."""
    if not any(cell.strip() for cell in row):
        return True
    symbol = _cell(row, columns, "symbol") or ""
    if symbol.lower().startswith(("total", "subtotal", "sub-total")):
        return True
    first = row[0].strip().lower() if row else ""
    return first.startswith(("total", "subtotal"))


def _document_text(raw: bytes) -> tuple[str, list[Table]]:
    parts = body_parts(raw)
    html = first_of(parts, "text/html")
    if html:
        return text_from_html(html), tables(html)
    plain = first_of(parts, "text/plain") or ""
    return plain, _text_tables(plain)


def _text_tables(plain: str) -> list[Table]:
    """Plain-text confirmations arrive as pipe-delimited tables."""
    rows: Table = []
    for line in plain.splitlines():
        if line.count("|") < 2:
            if rows:
                break
            continue
        rows.append([cell.strip() for cell in line.strip().strip("|").split("|")])
    return [rows] if rows else []


def _context(text: str) -> tuple[str, str | None]:
    currency_match = _BASE_CCY_RE.search(text)
    currency = currency_match.group(1).upper() if currency_match else "USD"
    account_match = _ACCOUNT_RE.search(text)
    return currency, account_match.group(0) if account_match else None


@dataclass(frozen=True, slots=True)
class IbkrTradeConfirmation:
    """Fills, as signed by the broker.

    Each row becomes a TRADE fact and, when commission is charged, a separate
    FEE fact — kept apart so gross and net can be computed from the same
    evidence without either one being backed out of the other.
    """

    id: str = "ibkr.trade_confirmation"
    version: str = "1.0.0"
    institution_id: str = "ibkr"
    doc_type: DocType = DocType.TRADE_CONFIRMATION

    def recognizes(self, raw: bytes) -> bool:
        lowered = raw.lower()
        looks_like_ibkr = b"interactive brokers" in lowered or b"ibkr" in lowered
        return looks_like_ibkr and (
            b"trade confirmation" in lowered or b"proceeds" in lowered
        )

    def extract(self, raw: bytes) -> ExtractionResult:
        try:
            text, all_tables = _document_text(raw)
        except Exception as exc:
            return ExtractionResult(status="failed", error=f"could not read body: {exc}")

        found = _find_table(all_tables, "symbol", "quantity", "proceeds")
        if found is None:
            return ExtractionResult(
                status="unsupported",
                error="no trades table with symbol, quantity and proceeds columns",
            )

        rows, columns = found
        default_currency, account_ref = _context(text)

        facts: list[ExtractedFact] = []
        skipped: list[str] = []

        for row in rows:
            if _is_noise(row, columns):
                continue

            symbol = _cell(row, columns, "symbol")
            quantity = parse_decimal(_cell(row, columns, "quantity"))
            proceeds = parse_decimal(_cell(row, columns, "proceeds"))
            as_of = parse_date(_cell(row, columns, "when"))
            currency = (_cell(row, columns, "currency") or default_currency).upper()

            if not symbol or quantity is None or proceeds is None or as_of is None:
                skipped.append(" | ".join(row))
                continue

            facts.append(
                ExtractedFact(
                    as_of=as_of,
                    kind=FactKind.TRADE,
                    currency=currency,
                    instrument=symbol,
                    quantity=quantity,
                    price=parse_decimal(_cell(row, columns, "price")),
                    amount_minor=to_minor(proceeds, currency),
                )
            )

            fee = parse_decimal(_cell(row, columns, "fee"))
            if fee is not None and fee != 0:
                facts.append(
                    ExtractedFact(
                        as_of=as_of,
                        kind=FactKind.FEE,
                        currency=currency,
                        instrument=symbol,
                        amount_minor=to_minor(fee, currency),
                        note="commission and exchange fees",
                    )
                )

        if not facts:
            return ExtractionResult(
                status="unsupported",
                error="trades table found but no row parsed cleanly",
                payload={"skipped_rows": skipped},
            )

        return ExtractionResult(
            status="ok",
            facts=tuple(facts),
            payload={
                "account_ref": account_ref,
                "base_currency": default_currency,
                "trade_rows": len(facts),
                "skipped_rows": skipped,
            },
        )


@dataclass(frozen=True, slots=True)
class IbkrActivityStatement:
    """NAV and external flows — the two series a TWR is actually made of.

    A return computed from NAV alone is wrong the moment money moves in or out,
    so the flows matter as much as the levels and are extracted together or not
    at all.
    """

    id: str = "ibkr.activity_statement"
    version: str = "1.0.0"
    institution_id: str = "ibkr"
    doc_type: DocType = DocType.STATEMENT

    def recognizes(self, raw: bytes) -> bool:
        lowered = raw.lower()
        return (b"interactive brokers" in lowered or b"ibkr" in lowered) and (
            b"net asset value" in lowered or b"activity statement" in lowered
        )

    def extract(self, raw: bytes) -> ExtractionResult:
        try:
            text, all_tables = _document_text(raw)
        except Exception as exc:
            return ExtractionResult(status="failed", error=f"could not read body: {exc}")

        currency, account_ref = _context(text)
        as_of = self._period_end(text)
        if as_of is None:
            return ExtractionResult(
                status="unsupported",
                error="no statement period or date found; a NAV without an as-of "
                "date cannot be placed in a series",
            )

        facts: list[ExtractedFact] = []

        nav = self._net_asset_value(all_tables)
        if nav is not None:
            facts.append(
                ExtractedFact(
                    as_of=as_of,
                    kind=FactKind.NAV,
                    currency=currency,
                    amount_minor=to_minor(nav, currency),
                    note="total net asset value at period end",
                )
            )

        facts.extend(self._flows(all_tables, currency, as_of))

        if not facts:
            return ExtractionResult(
                status="unsupported",
                error="statement recognized but neither NAV nor flows could be read",
            )

        return ExtractionResult(
            status="ok",
            facts=tuple(facts),
            payload={
                "account_ref": account_ref,
                "base_currency": currency,
                "period_end": as_of.isoformat(),
                "has_nav": nav is not None,
            },
        )

    @staticmethod
    def _period_end(text: str) -> date | None:
        """A NAV without an as-of date cannot be placed in a series, so this
        either finds the real period end or gives up and says so."""
        match = _PERIOD_RE.search(text)
        if match:
            parsed = parse_date(match.group(2))  # the end of the range
            if parsed:
                return parsed
        match = _STATEMENT_DATE_RE.search(text)
        if match:
            parsed = parse_date(match.group(1))
            if parsed:
                return parsed
        return None

    @staticmethod
    def _net_asset_value(all_tables: list[Table]) -> Decimal | None:
        for table in all_tables:
            header_index = None
            total_column = None
            for idx, row in enumerate(table[:3]):
                for col, cell in enumerate(row):
                    if normalize_header(cell) in {"current total", "total", "ending value"}:
                        header_index, total_column = idx, col
                        break
                if header_index is not None:
                    break
            if header_index is None or total_column is None:
                continue
            for row in table[header_index + 1 :]:
                if not row:
                    continue
                if row[0].strip().lower() in {"total", "net asset value", "total nav"}:
                    if total_column < len(row):
                        value = parse_decimal(row[total_column])
                        if value is not None:
                            return value
        return None

    @staticmethod
    def _flows(
        all_tables: list[Table], currency: str, fallback_date: date
    ) -> list[ExtractedFact]:
        # Quantity is what makes a table a trades table. Excluding it is how we
        # avoid reading fills as deposits.
        found = _find_table(all_tables, "when", "proceeds", exclude=("quantity",))
        if found is None:
            return []
        rows, columns = found

        flows: list[ExtractedFact] = []
        for row in rows:
            if _is_noise(row, columns):
                continue
            amount = parse_decimal(_cell(row, columns, "proceeds"))
            if amount is None or amount == 0:
                continue
            row_currency = (_cell(row, columns, "currency") or currency).upper()
            flows.append(
                ExtractedFact(
                    as_of=parse_date(_cell(row, columns, "when")) or fallback_date,
                    kind=FactKind.CASH_FLOW,
                    currency=row_currency,
                    amount_minor=to_minor(amount, row_currency),
                    note="deposit" if amount > 0 else "withdrawal",
                )
            )
        return flows


TRADE_CONFIRMATION = registry.register(IbkrTradeConfirmation())
ACTIVITY_STATEMENT = registry.register(IbkrActivityStatement())
