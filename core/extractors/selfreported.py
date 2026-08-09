"""CSV that somebody typed.

This exists so that imported data can be graded honestly rather than refused.
A manager with eleven signed months and one month that only exists in a
spreadsheet should be able to show all twelve — with the twelfth marked for
what it is, and with every metric spanning it capped at `self_reported`.

That will feel punitive, and it is exactly right. The alternative is a number
that looks as strong as its strongest input.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass

from core.extraction.base import ExtractedFact, ExtractionResult, registry
from core.extractors.numbers import normalize_header, parse_date, parse_decimal, to_minor
from core.types import DocType, FactKind

INSTITUTION_ID = "self-reported"

_NAV_ALIASES = {"nav", "net asset value", "value", "amount", "total"}
_DATE_ALIASES = {"as_of", "as of", "date", "period_end", "period end"}
_CCY_ALIASES = {"currency", "ccy"}


@dataclass(frozen=True, slots=True)
class SelfReportedNavCsv:
    id: str = "self.nav_csv"
    version: str = "1.0.0"
    institution_id: str = INSTITUTION_ID
    doc_type: DocType = DocType.STATEMENT

    def recognizes(self, raw: bytes) -> bool:
        head = raw[:2048].decode("utf-8", errors="replace").lower()
        first_line = head.splitlines()[0] if head.splitlines() else ""
        if "," not in first_line:
            return False
        headers = {normalize_header(h) for h in first_line.split(",")}
        return bool(headers & _DATE_ALIASES) and bool(headers & _NAV_ALIASES)

    def extract(self, raw: bytes) -> ExtractionResult:
        text = raw.decode("utf-8", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            return ExtractionResult(status="unsupported", error="no CSV header row")

        columns = {normalize_header(name): name for name in reader.fieldnames}
        date_column = _pick(columns, _DATE_ALIASES)
        nav_column = _pick(columns, _NAV_ALIASES)
        ccy_column = _pick(columns, _CCY_ALIASES)

        if date_column is None or nav_column is None:
            return ExtractionResult(
                status="unsupported",
                error="CSV needs a date column and a NAV column",
            )

        facts: list[ExtractedFact] = []
        skipped: list[str] = []
        for row in reader:
            as_of = parse_date(row.get(date_column))
            amount = parse_decimal(row.get(nav_column))
            if as_of is None or amount is None:
                skipped.append(",".join(f"{k}={v}" for k, v in row.items()))
                continue
            currency = (row.get(ccy_column) if ccy_column else None) or "USD"
            currency = currency.strip().upper()
            facts.append(
                ExtractedFact(
                    as_of=as_of,
                    kind=FactKind.NAV,
                    currency=currency,
                    amount_minor=to_minor(amount, currency),
                    note="self-reported: no institution vouches for this figure",
                )
            )

        if not facts:
            return ExtractionResult(
                status="unsupported",
                error="no CSV row parsed cleanly",
                payload={"skipped_rows": skipped},
            )

        return ExtractionResult(
            status="ok",
            facts=tuple(facts),
            payload={
                "rows": len(facts),
                "skipped_rows": skipped,
                "base_currency": facts[0].currency,
                "account_ref": None,
            },
        )


def _pick(columns: dict[str, str], aliases: set[str]) -> str | None:
    for normalized, original in columns.items():
        if normalized in aliases:
            return original
    return None


NAV_CSV = registry.register(SelfReportedNavCsv())
