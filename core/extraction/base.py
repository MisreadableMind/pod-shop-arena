"""Extraction: our reading of a document, kept strictly apart from the proof
that the document is genuine.

DKIM proves the bytes left the institution. It says nothing about whether our
parser read `NAV: 41,207,338.22` correctly. So extractors are pure, versioned
functions, the version travels with every fact, and a viewer can always pull the
original signed document and check our reading against it.

An extractor cannot know how strong its own evidence is, so it never sets a
tier. It emits `ExtractedFact`, and the pipeline binds the account and the tier
that the verify step assigned.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable

from core.tiers import Tier
from core.types import DocType, Fact, FactKind


@dataclass(frozen=True, slots=True)
class ExtractedFact:
    """A reading, before it has been told whose account it belongs to or how
    much anybody should believe it."""

    as_of: date
    kind: FactKind
    currency: str
    instrument: str | None = None
    quantity: Decimal | None = None
    price: Decimal | None = None
    amount_minor: int | None = None
    note: str | None = None

    def bind(
        self, *, account_id: str, document_sha256: str, tier: Tier, extractor_version: str
    ) -> Fact:
        return Fact(
            account_id=account_id,
            document_sha256=document_sha256,
            as_of=self.as_of,
            kind=self.kind,
            tier=tier,
            currency=self.currency,
            instrument=self.instrument,
            quantity=self.quantity,
            price=self.price,
            amount_minor=self.amount_minor,
            extractor_version=extractor_version,
            note=self.note,
        )


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    status: str  # "ok" | "unsupported" | "failed"
    facts: tuple[ExtractedFact, ...] = ()
    payload: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == "ok"


@runtime_checkable
class Extractor(Protocol):
    """`(institution, doc_type, version) -> Fact[]`, and nothing else.

    Pure by contract: no clock, no network, no database. Given the same bytes it
    must return the same facts forever, because a fact's hash is committed
    on-chain and re-deriving it must reproduce that hash exactly.
    """

    id: str
    version: str
    institution_id: str
    doc_type: DocType

    def recognizes(self, raw: bytes) -> bool: ...

    def extract(self, raw: bytes) -> ExtractionResult: ...


class Registry:
    """Extractors keyed by institution and document type.

    Versions are never overwritten in place. Fixing a parser means registering a
    new version and re-deriving; the original evidence never changes and the old
    root stays honest about what the old code read.
    """

    def __init__(self) -> None:
        self._by_key: dict[tuple[str, DocType], Extractor] = {}

    def register(self, extractor: Extractor) -> Extractor:
        key = (extractor.institution_id, extractor.doc_type)
        if key in self._by_key:
            existing = self._by_key[key]
            raise ValueError(
                f"{existing.id} already handles {key}; register a new doc_type "
                "or supersede it explicitly"
            )
        self._by_key[key] = extractor
        return extractor

    def for_document(
        self, institution_id: str | None, doc_type: DocType
    ) -> Extractor | None:
        if institution_id is None:
            return None
        return self._by_key.get((institution_id, doc_type))

    def sniff(self, institution_id: str | None, raw: bytes) -> Extractor | None:
        """Find an extractor that recognizes these bytes, when the document type
        was not declared up front."""
        for (inst, _), extractor in self._by_key.items():
            if institution_id is not None and inst != institution_id:
                continue
            if extractor.recognizes(raw):
                return extractor
        return None

    def versions(self) -> dict[str, str]:
        return {e.id: e.version for e in self._by_key.values()}

    def all(self) -> tuple[Extractor, ...]:
        return tuple(self._by_key.values())


registry = Registry()
