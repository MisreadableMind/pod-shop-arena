"""Domain types. Pure data plus the one rule each type is responsible for.

Every type that ends up in the Merkle tree defines `canonical_form()`, and that
projection — not the Python object — is what gets hashed. Adding a field to a
dataclass therefore does not silently change historical roots; changing
`canonical_form()` does, which is exactly the decision we want to be loud.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from core.tiers import Tier


class Channel(str, Enum):
    """How evidence reached us."""

    EML_UPLOAD = "eml_upload"
    MAIL_INTAKE = "mail_intake"
    IBKR_FLEX = "ibkr_flex"
    ADMIN_SFTP = "admin_sftp"
    CSV_UPLOAD = "csv_upload"
    MANUAL = "manual"


# The strongest tier a channel could ever justify, before we look at the
# evidence itself. The actual tier is min(ceiling, what the evidence proves).
_CEILINGS: dict[Channel, Tier] = {
    Channel.EML_UPLOAD: Tier.SOURCE_SIGNED,
    Channel.MAIL_INTAKE: Tier.SOURCE_SIGNED,
    Channel.IBKR_FLEX: Tier.AGGREGATOR_ATTESTED,
    Channel.ADMIN_SFTP: Tier.AGGREGATOR_ATTESTED,
    Channel.CSV_UPLOAD: Tier.SELF_REPORTED,
    Channel.MANUAL: Tier.SELF_REPORTED,
}


def channel_ceiling(channel: Channel) -> Tier:
    return _CEILINGS[channel]


def tier_for(channel: Channel, dkim_verified: bool | None) -> Tier:
    """The one place a tier is ever assigned.

    A mail channel earns `source_signed` only when the institution's signature
    actually verified. A failed signature does not fall back to
    `aggregator_attested` — nobody attested to anything — it falls all the way
    to `self_reported`, because at that point the only reason to believe the
    document is that somebody uploaded it.
    """
    ceiling = channel_ceiling(channel)
    if channel in (Channel.EML_UPLOAD, Channel.MAIL_INTAKE):
        return ceiling if dkim_verified else Tier.SELF_REPORTED
    return ceiling


class DocType(str, Enum):
    TRADE_CONFIRMATION = "trade_confirmation"
    STATEMENT = "statement"
    NAV_NOTICE = "nav_notice"
    UNKNOWN = "unknown"


class FactKind(str, Enum):
    TRADE = "trade"
    POSITION = "position"
    NAV = "nav"
    CASH_FLOW = "cash_flow"
    FEE = "fee"


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class Institution:
    """Who we will believe a signature from.

    `domains` is the allow-list matched against DKIM `d=`. A signature from
    anywhere else — Gmail's on a forward, say — proves that party handled the
    mail and nothing an allocator cares about.
    """

    id: str
    name: str
    domains: tuple[str, ...]
    doc_types: tuple[DocType, ...] = ()

    def signs_for(self, d_domain: str) -> bool:
        candidate = d_domain.lower().rstrip(".")
        return any(
            candidate == d or candidate.endswith("." + d)
            for d in (dom.lower() for dom in self.domains)
        )


@dataclass(frozen=True, slots=True)
class Document:
    """Raw evidence, write-once. `sha256` is over the bytes exactly as received;
    the blob store is keyed by it, so identical content is a no-op on re-ingest."""

    sha256: str
    blob_key: str
    byte_length: int
    received_at: datetime
    channel: Channel
    institution_id: str | None = None
    doc_type: DocType = DocType.UNKNOWN

    def canonical_form(self) -> dict[str, Any]:
        return {
            "sha256": self.sha256,
            "byte_length": self.byte_length,
            "channel": self.channel.value,
            "institution_id": self.institution_id,
            "doc_type": self.doc_type.value,
        }


@dataclass(frozen=True, slots=True)
class DkimVerdict:
    """The cryptographic half of the story, and the captured key that keeps it
    checkable after the selector leaves DNS.

    `dns_txt_record` is the whole point of anchoring: a signature we can verify
    today is unverifiable in a year once the selector is retired, unless someone
    wrote the key down at the time and committed to it.
    """

    verified: bool
    d_domain: str | None
    selector: str | None
    algo: str | None
    l_tag_present: bool
    dns_txt_record: str | None
    dns_captured_at: datetime | None
    body_hash_matched: bool = False
    signed_headers: tuple[str, ...] = ()
    failure_reason: str | None = None

    @property
    def dns_record_hash(self) -> str | None:
        if self.dns_txt_record is None:
            return None
        from core.canonical import sha256_hex

        return sha256_hex(self.dns_txt_record.encode("utf-8"))

    def canonical_form(self) -> dict[str, Any]:
        return {
            "verified": self.verified,
            "d_domain": self.d_domain,
            "selector": self.selector,
            "algo": self.algo,
            "l_tag_present": self.l_tag_present,
            "dns_record_hash": self.dns_record_hash,
            "dns_captured_at": self.dns_captured_at,
            "body_hash_matched": self.body_hash_matched,
            "signed_headers": list(self.signed_headers),
            "failure_reason": self.failure_reason,
        }


@dataclass(frozen=True, slots=True)
class Extraction:
    """Our reading of a document. Deliberately a separate object from the
    verdict above: DKIM proves the bytes left the institution, and says nothing
    at all about whether our parser understood them."""

    document_sha256: str
    extractor_id: str
    extractor_version: str
    status: str  # "ok" | "unsupported" | "failed"
    payload: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def canonical_form(self) -> dict[str, Any]:
        return {
            "document_sha256": self.document_sha256,
            "extractor_id": self.extractor_id,
            "extractor_version": self.extractor_version,
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class Fact:
    """One observation, pointing back at the document that justifies it.

    A fact never carries a tier of its own choosing — it inherits the tier of
    its document, assigned once at the verify step.

    Note on `price` vs `amount_minor`. Amounts are money and follow the rule:
    integer minor units, never a float. A per-unit price is not an amount — FX
    and futures quote well past two decimals, and squeezing 182.4750 into cents
    would destroy real precision inside a hashed object. So price is a Decimal,
    which `canonical.py` pins to a fixed scale and is every bit as deterministic
    as an integer. The rule the plan actually cares about — no floats anywhere —
    holds either way.
    """

    account_id: str
    document_sha256: str
    as_of: date
    kind: FactKind
    tier: Tier
    currency: str
    instrument: str | None = None
    quantity: Decimal | None = None
    price: Decimal | None = None
    amount_minor: int | None = None
    extractor_version: str | None = None
    note: str | None = None

    def canonical_form(self) -> dict[str, Any]:
        return {
            "account_id": self.account_id,
            "document_sha256": self.document_sha256,
            "as_of": self.as_of,
            "kind": self.kind.value,
            "tier": self.tier.slug,
            "currency": self.currency,
            "instrument": self.instrument,
            "quantity": self.quantity,
            "price": self.price,
            "amount_minor": self.amount_minor,
            "extractor_version": self.extractor_version,
        }


@dataclass(frozen=True, slots=True)
class MetricResult:
    """A number, the formula that produced it, what fed it, and how strong the
    weakest input was. Never displayed without the tier."""

    key: str
    value: Decimal
    unit: str
    formula: str
    tier: Tier
    inputs: dict[str, Any] = field(default_factory=dict)
    basis: str = "net"  # "net" | "gross"

    def canonical_form(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "unit": self.unit,
            "formula": self.formula,
            "tier": self.tier.slug,
            "basis": self.basis,
            "inputs": self.inputs,
        }


@dataclass(frozen=True, slots=True)
class Finding:
    """A disagreement between two sources covering the same period.

    Written, never thrown. Allocators care more about the discrepancies we
    surface than the ones we hide.
    """

    kind: str
    severity: Severity
    detail: str
    as_of: date | None = None

    def canonical_form(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "severity": self.severity.value,
            "detail": self.detail,
            "as_of": self.as_of,
        }
