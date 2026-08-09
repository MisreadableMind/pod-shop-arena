"""Turning printed numbers and dates back into exact values.

Everything here is strict about one thing: it never produces a float. A number
that cannot be read exactly comes back as None and the caller decides what that
means, which is better than a plausible wrong number entering a hashed fact.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN

from core.money import exponent_for

_CURRENCY_JUNK = re.compile(r"[$£€¥,\s ]")
_TRAILING_CCY = re.compile(r"\s*[A-Z]{3}\s*$")


def parse_decimal(text: str | None) -> Decimal | None:
    """Read a printed number exactly, or not at all.

    Handles thousands separators, currency symbols, unicode minus, and the
    accounting convention where a negative is wrapped in parentheses.
    """
    if text is None:
        return None
    cleaned = text.strip()
    if not cleaned or cleaned in {"-", "--", "—", "n/a", "N/A"}:
        return None

    cleaned = _TRAILING_CCY.sub("", cleaned)

    negative = False
    if cleaned.startswith("(") and cleaned.endswith(")"):
        negative = True
        cleaned = cleaned[1:-1]

    cleaned = cleaned.replace("−", "-")  # unicode minus
    cleaned = _CURRENCY_JUNK.sub("", cleaned)
    if not cleaned or cleaned in {"-", "+"}:
        return None

    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None
    if not value.is_finite():
        return None
    return -value if negative else value


def to_minor(amount: Decimal, currency: str) -> int:
    """Money to integer minor units, quantized deliberately.

    Rounding happens here, once, in the open — rather than accumulating silently
    somewhere downstream where nobody can point at it.
    """
    exponent = exponent_for(currency)
    scaled = (amount * (10**exponent)).quantize(Decimal(1), rounding=ROUND_HALF_EVEN)
    return int(scaled)


_DATE_PATTERNS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%d-%b-%y",
    "%d-%b-%Y",
    "%B %d, %Y",
    "%b %d, %Y",
    "%d %B %Y",
)


def parse_date(text: str | None) -> date | None:
    """Read the date part of a printed timestamp.

    Ambiguous formats are a real hazard here — 03/04/2026 is two different days
    depending on which side of the Atlantic printed it — so ISO is tried first
    and the fallbacks are ordered by what the institution in question actually
    emits.
    """
    if not text:
        return None
    cleaned = text.strip()

    # Try the whole string before trimming anything. "October 31, 2025" carries
    # a comma that is part of the date, not a separator before a time, and
    # splitting on it first turns a valid date into "October 31".
    for candidate in (cleaned, _strip_time(cleaned)):
        for pattern in _DATE_PATTERNS:
            try:
                return datetime.strptime(candidate, pattern).date()
            except ValueError:
                continue
    return None


_TIME_SUFFIX = re.compile(r"[,;]?\s*\d{1,2}:\d{2}(:\d{2})?(\s*[AP]\.?M\.?)?\s*$", re.I)


def _strip_time(text: str) -> str:
    """Drop a trailing clock time: `2026-07-14, 09:31:04` is a date to us."""
    return _TIME_SUFFIX.sub("", text).strip().rstrip(",").strip()


def normalize_header(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower().rstrip(":")
