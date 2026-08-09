"""Canonical serialization. The determinism contract starts here.

Every hash in the system is taken over bytes produced by this module, so two
machines that disagree about how to write a number would produce two different
Merkle roots for identical evidence — and the anchor would be worthless. Hence
the rules: sorted keys, no insignificant whitespace, Decimals pinned to a fixed
scale, timestamps normalized to UTC, and a flat refusal to serialize any type we
have not thought about. Especially float.
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone
from decimal import Context, Decimal, ROUND_HALF_EVEN
from enum import Enum
from typing import Any

# Every Decimal is written at exactly this scale, so Decimal("1.1") and
# Decimal("1.10") — equal numbers, different objects — hash identically.
CANONICAL_EXPONENT = Decimal("1E-12")
_CTX = Context(prec=60, rounding=ROUND_HALF_EVEN)

_LEAF_DOMAIN = b"podarena.leaf.v1"


class NotCanonical(TypeError):
    """A value reached the serializer that has no single obvious byte form."""


def canonical_decimal(value: Decimal) -> str:
    if not isinstance(value, Decimal):
        raise NotCanonical(f"expected Decimal, got {type(value).__name__}")
    if not value.is_finite():
        raise NotCanonical(f"cannot canonicalize non-finite Decimal: {value}")
    quantized = _CTX.quantize(value, CANONICAL_EXPONENT)
    if quantized == 0:
        # Decimal keeps a sign on zero; "-0.000000000000" and "0.000000000000"
        # are the same number and must be the same bytes.
        quantized = abs(quantized)
    return format(quantized, "f")


def canonical_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        raise NotCanonical(
            "naive datetime has no canonical form; attach a timezone at the edge"
        )
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _encode(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, float):
        raise NotCanonical(
            "float is not serializable here; use Decimal for ratios and "
            "integer minor units for money"
        )
    if isinstance(value, int):
        return str(value)
    if isinstance(value, Decimal):
        return f'"{canonical_decimal(value)}"'
    if isinstance(value, str):
        return _encode_string(value)
    if isinstance(value, (bytes, bytearray)):
        return f'"{bytes(value).hex()}"'
    if isinstance(value, datetime):
        return f'"{canonical_datetime(value)}"'
    if isinstance(value, date):
        return f'"{value.isoformat()}"'
    if isinstance(value, Enum):
        # Enum members serialize by name, so renumbering an enum can never
        # silently change a historical hash.
        return _encode_string(value.name.lower())
    if isinstance(value, dict):
        for key in value:
            if not isinstance(key, str):
                raise NotCanonical(f"object keys must be str, got {type(key).__name__}")
        items = ",".join(
            f"{_encode_string(k)}:{_encode(value[k])}" for k in sorted(value)
        )
        return "{" + items + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_encode(v) for v in value) + "]"
    if hasattr(value, "canonical_form"):
        return _encode(value.canonical_form())
    raise NotCanonical(f"no canonical form defined for {type(value).__name__}")


_ESCAPES = {
    '"': '\\"',
    "\\": "\\\\",
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
    "\b": "\\b",
    "\f": "\\f",
}


def _encode_string(value: str) -> str:
    out = ['"']
    for ch in value:
        if ch in _ESCAPES:
            out.append(_ESCAPES[ch])
        elif ord(ch) < 0x20:
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def canonical(value: Any) -> bytes:
    """The one true byte form of a value."""
    return _encode(value).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def leaf_hash(kind: str, value: Any) -> bytes:
    """Hash a value as a Merkle leaf of a named kind.

    The kind is mixed in so a document hash can never be mistaken for a fact
    hash, even if the two happened to serialize to the same bytes.
    """
    payload = _LEAF_DOMAIN + b"\x00" + kind.encode("ascii") + b"\x00" + canonical(value)
    return hashlib.sha256(payload).digest()
