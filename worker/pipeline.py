"""The ingest pipeline: seven numbered steps, each pure where it can be.

Receive · Verify · Extract · Normalize · Reconcile · Compute · Commit.

It runs inline rather than on a queue. A single message takes milliseconds to
verify and parse, and anchoring on Monad confirms in well under a second, so a
worker and a broker would add two moving parts and a class of "the job is
somewhere" bugs in exchange for nothing a user would notice. The orchestrator
below is a plain function, so putting it behind a queue later is a change of
caller, not a rewrite.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from adapters import db
from adapters.blobs import blob_store
from adapters.chain import chain_client, record_key
from adapters.config import settings
from adapters.dns import ChainResolver, DnsResolver, LiveResolver, StaticResolver
from core import METHODOLOGY_VERSION
from core.dkim import DkimAnalysis, required_dns_names, verify_message
from core.extraction import registry
from core.extractors import INSTITUTIONS
from core.metrics import Config, InsufficientSeries, Uncomputable, build_series, compute
from core.reconcile import reconcile
from core.snapshot import Snapshot, build_snapshot
from core.tiers import Tier
from core.types import (
    Channel,
    DkimVerdict,
    DocType,
    Document,
    Fact,
    FactKind,
    Finding,
    Institution,
    MetricResult,
    Severity,
    tier_for,
)


def active_institutions() -> tuple[Institution, ...]:
    """The DKIM allow-list actually in force.

    The demo domain is bolted on here, at the edge, and only when the fixture
    flag is set — never inside `core.extractors`, so a production deployment
    cannot inherit a test domain by accident.
    """
    if settings().demo_fixtures:
        from demo.corpus import demo_institutions

        return demo_institutions()
    return INSTITUTIONS


def default_resolver() -> DnsResolver:
    """Live DNS, falling back to whatever the fixture corpus captured."""
    if settings().demo_fixtures:
        return ChainResolver(LiveResolver(), StaticResolver(_fixture_dns()))
    return LiveResolver()


_FIXTURE_DNS: dict[str, str] | None = None


def _fixture_dns() -> dict[str, str]:
    global _FIXTURE_DNS
    if _FIXTURE_DNS is None:
        from demo.corpus import load_or_build

        _FIXTURE_DNS = load_or_build(settings().fixture_dir).captured_dns
    return _FIXTURE_DNS


def set_fixture_dns(records: dict[str, str]) -> None:
    """The seed script generates one corpus and shares its keys with ingest."""
    global _FIXTURE_DNS
    _FIXTURE_DNS = dict(records)


@dataclass
class IngestOutcome:
    document_id: str
    sha256: str
    duplicate: bool
    tier: Tier
    verified: bool
    doc_type: str
    institution_id: str | None
    facts_written: int
    analysis: DkimAnalysis | None = None
    extraction_status: str = "skipped"
    extraction_error: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "document_id": self.document_id,
            "sha256": self.sha256,
            "duplicate": self.duplicate,
            "tier": self.tier.slug,
            "verified": self.verified,
            "doc_type": self.doc_type,
            "institution_id": self.institution_id,
            "facts_written": self.facts_written,
            "extraction_status": self.extraction_status,
            "extraction_error": self.extraction_error,
            "dkim": {
                "verified": self.analysis.verdict.verified if self.analysis else False,
                "d_domain": self.analysis.verdict.d_domain if self.analysis else None,
                "selector": self.analysis.verdict.selector if self.analysis else None,
                "l_tag_present": self.analysis.verdict.l_tag_present
                if self.analysis
                else False,
                "dns_record_hash": self.analysis.verdict.dns_record_hash
                if self.analysis
                else None,
                "failure_reason": self.analysis.verdict.failure_reason
                if self.analysis
                else None,
                "signatures": [s.as_dict() for s in self.analysis.summaries]
                if self.analysis
                else [],
            },
        }


# -- steps 1 to 4 ---------------------------------------------------------


def ingest(
    session: Session,
    *,
    entity_id: str,
    record_id: str,
    raw: bytes,
    channel: Channel = Channel.EML_UPLOAD,
    filename: str | None = None,
    resolver: DnsResolver | None = None,
    now: datetime | None = None,
) -> IngestOutcome:
    now = now or datetime.now(timezone.utc)
    resolver = resolver or default_resolver()

    # 1. Receive. Hash first; the hash is the identity of the evidence.
    sha256 = hashlib.sha256(raw).hexdigest()
    existing = session.scalar(
        select(db.Document).where(
            db.Document.sha256 == sha256, db.Document.entity_id == entity_id
        )
    )
    if existing is not None:
        return IngestOutcome(
            document_id=existing.id,
            sha256=sha256,
            duplicate=True,
            tier=Tier.from_slug(_document_tier(session, existing.id)),
            verified=_document_verified(session, existing.id),
            doc_type=existing.doc_type,
            institution_id=existing.institution_id,
            facts_written=0,
        )

    blob_key = blob_store().put(raw)

    # 2. Verify. DNS names come from the signature, an adapter resolves them,
    #    and the pure verifier judges. The captured record is stored, because
    #    once the selector is retired it is the only thing keeping the
    #    signature checkable.
    names = required_dns_names(raw)
    records = resolver.txt(names) if names else {}
    analysis = verify_message(
        raw,
        dns_records=records,
        institutions=active_institutions(),
        captured_at=now,
    )
    verdict = analysis.verdict
    institution = analysis.institution

    # Tier is assigned here and nowhere else.
    tier = tier_for(channel, verdict.verified)

    # 3. Extract. Independent of the verdict: a tampered document still parses,
    #    it just parses as self-reported. Refusing to read it would hide the
    #    tamper rather than grade it.
    extractor = registry.sniff(institution.id if institution else None, raw)
    if extractor is None:
        extractor = registry.sniff(None, raw)

    doc_type = extractor.doc_type if extractor else DocType.UNKNOWN

    document = db.Document(
        entity_id=entity_id,
        record_id=record_id,
        sha256=sha256,
        blob_key=blob_key,
        byte_length=len(raw),
        received_at=now,
        channel=channel.value,
        institution_id=institution.id if institution else None,
        doc_type=doc_type.value,
        filename=filename,
    )
    session.add(document)
    session.flush()

    session.add(
        db.DkimVerdictRow(
            document_id=document.id,
            verified=verdict.verified,
            d_domain=verdict.d_domain,
            selector=verdict.selector,
            algo=verdict.algo,
            l_tag_present=verdict.l_tag_present,
            body_hash_matched=verdict.body_hash_matched,
            dns_txt_record=verdict.dns_txt_record,
            dns_captured_at=verdict.dns_captured_at,
            signed_headers=list(verdict.signed_headers),
            signature_summaries=[s.as_dict() for s in analysis.summaries],
            failure_reason=verdict.failure_reason,
        )
    )

    if extractor is None:
        session.flush()
        return IngestOutcome(
            document_id=document.id,
            sha256=sha256,
            duplicate=False,
            tier=tier,
            verified=verdict.verified,
            doc_type=doc_type.value,
            institution_id=institution.id if institution else None,
            facts_written=0,
            analysis=analysis,
            extraction_status="unsupported",
            extraction_error="no extractor recognizes this document",
        )

    result = extractor.extract(raw)
    session.add(
        db.ExtractionRow(
            document_id=document.id,
            extractor_id=extractor.id,
            extractor_version=extractor.version,
            status=result.status,
            payload=_jsonable(result.payload),
            error=result.error,
        )
    )

    # 4. Normalize. Facts inherit the document's tier; nothing here may raise it.
    written = 0
    if result.ok and result.facts:
        account = _account_for(
            session,
            entity_id=entity_id,
            institution_id=extractor.institution_id,
            external_ref=result.payload.get("account_ref"),
            currency=result.payload.get("base_currency", "USD"),
        )
        for extracted in result.facts:
            fact = extracted.bind(
                account_id=account.id,
                document_sha256=sha256,
                tier=tier,
                extractor_version=extractor.version,
            )
            session.add(
                db.FactRow(
                    record_id=record_id,
                    account_id=account.id,
                    document_id=document.id,
                    as_of=fact.as_of,
                    kind=fact.kind.value,
                    instrument=fact.instrument,
                    quantity=fact.quantity,
                    price=fact.price,
                    amount_minor=fact.amount_minor,
                    currency=fact.currency,
                    tier=fact.tier.slug,
                    extractor_version=fact.extractor_version,
                    note=fact.note,
                )
            )
            written += 1

    session.flush()
    return IngestOutcome(
        document_id=document.id,
        sha256=sha256,
        duplicate=False,
        tier=tier,
        verified=verdict.verified,
        doc_type=doc_type.value,
        institution_id=institution.id if institution else None,
        facts_written=written,
        analysis=analysis,
        extraction_status=result.status,
        extraction_error=result.error,
    )


# -- steps 5 to 7 ---------------------------------------------------------


@dataclass
class SnapshotOutcome:
    snapshot: Snapshot
    snapshot_id: str
    metrics: tuple[MetricResult, ...]
    findings: tuple[Finding, ...]
    anchor_status: str
    tx_hash: str | None = None
    block_number: int | None = None
    chain_seq: int | None = None
    anchor_error: str | None = None


def rebuild(
    session: Session,
    *,
    record_id: str,
    config: Config | None = None,
    anchor: bool = True,
) -> SnapshotOutcome:
    """Recompute a record from its evidence and commit the result.

    Everything downstream of the facts is derived, every time. There is no
    incremental update path on purpose: a cached metric that disagrees with the
    evidence is worse than a slow one.
    """
    record = session.get(db.Record, record_id)
    if record is None:
        raise LookupError(f"no record {record_id}")

    fact_rows = list(
        session.scalars(
            select(db.FactRow)
            .where(db.FactRow.record_id == record_id)
            .order_by(db.FactRow.as_of, db.FactRow.id)
        )
    )
    documents, verdicts = _evidence(session, record_id)
    facts = tuple(_to_fact(row) for row in fact_rows)

    # 5. Reconcile. Conflicts are written down, not raised.
    findings = list(reconcile(facts))

    # 6. Compute.
    metrics: tuple[MetricResult, ...] = ()
    if facts:
        try:
            series = build_series(facts)
            metrics = compute(series, config or Config())
        except (InsufficientSeries, Uncomputable) as exc:
            findings.append(
                Finding(
                    kind="metrics_uncomputable",
                    severity=Severity.WARNING,
                    detail=str(exc),
                )
            )

    extractor_versions = registry.versions()

    seq = (
        session.scalar(
            select(db.Snapshot.seq)
            .where(db.Snapshot.record_id == record_id)
            .order_by(db.Snapshot.seq.desc())
            .limit(1)
        )
        or 0
    ) + 1

    snapshot = build_snapshot(
        record_id=record.slug,
        seq=seq,
        documents=documents,
        verdicts=verdicts,
        facts=facts,
        metrics=metrics,
        methodology_version=METHODOLOGY_VERSION,
        extractor_versions=extractor_versions,
        findings=tuple(findings),
    )

    row = db.Snapshot(
        record_id=record_id,
        seq=seq,
        root=snapshot.root_hex,
        metrics_hash=snapshot.metrics_hash,
        methodology_version=METHODOLOGY_VERSION,
        extractor_versions=extractor_versions,
        tier=snapshot.tier.slug,
        leaves=[leaf.as_dict() for leaf in snapshot.leaves],
    )
    session.add(row)
    session.flush()

    for metric in metrics:
        session.add(
            db.MetricRow(
                snapshot_id=row.id,
                key=metric.key,
                basis=metric.basis,
                value=metric.value,
                unit=metric.unit,
                formula=metric.formula,
                inputs=_jsonable(metric.inputs),
                tier=metric.tier.slug,
            )
        )
    for finding in findings:
        session.add(
            db.FindingRow(
                snapshot_id=row.id,
                kind=finding.kind,
                severity=finding.severity.value,
                detail=finding.detail,
                as_of=finding.as_of,
            )
        )

    # 7. Commit.
    receipt = None
    if anchor:
        receipt = chain_client().anchor(record.chain_key, snapshot.root_hex)
        session.add(
            db.Anchor(
                snapshot_id=row.id,
                chain_id=settings().chain_id,
                root=snapshot.root_hex,
                seq=seq,
                status=receipt.status,
                tx_hash=receipt.tx_hash,
                block_number=receipt.block_number,
                confirmed_at=receipt.confirmed_at,
                error=receipt.error,
            )
        )

    session.flush()
    return SnapshotOutcome(
        snapshot=snapshot,
        snapshot_id=row.id,
        metrics=metrics,
        findings=tuple(findings),
        anchor_status=receipt.status if receipt else "not_attempted",
        tx_hash=receipt.tx_hash if receipt else None,
        block_number=receipt.block_number if receipt else None,
        chain_seq=receipt.seq if receipt else None,
        anchor_error=receipt.error if receipt else None,
    )


# -- helpers --------------------------------------------------------------


def _evidence(
    session: Session, record_id: str
) -> tuple[list[Document], list[tuple[str, DkimVerdict]]]:
    """Every document held for this record, and what we made of its signature.

    Documents that produced no facts are still committed to. A tampered message
    we rejected is evidence of the rejection, and dropping it from the tree
    would let us quietly forget having seen it.
    """
    rows = list(
        session.scalars(
            select(db.Document)
            .where(db.Document.record_id == record_id)
            .order_by(db.Document.sha256)
        )
    )
    documents = [
        Document(
            sha256=row.sha256,
            blob_key=row.blob_key,
            byte_length=row.byte_length,
            received_at=db.as_utc(row.received_at),
            channel=Channel(row.channel),
            institution_id=row.institution_id,
            doc_type=DocType(row.doc_type),
        )
        for row in rows
    ]

    verdicts: list[tuple[str, DkimVerdict]] = []
    by_id = {row.id: row.sha256 for row in rows}
    if by_id:
        for verdict_row in session.scalars(
            select(db.DkimVerdictRow).where(
                db.DkimVerdictRow.document_id.in_(list(by_id))
            )
        ):
            verdicts.append(
                (
                    by_id[verdict_row.document_id],
                    DkimVerdict(
                        verified=verdict_row.verified,
                        d_domain=verdict_row.d_domain,
                        selector=verdict_row.selector,
                        algo=verdict_row.algo,
                        l_tag_present=verdict_row.l_tag_present,
                        dns_txt_record=verdict_row.dns_txt_record,
                        dns_captured_at=db.as_utc(verdict_row.dns_captured_at),
                        body_hash_matched=verdict_row.body_hash_matched,
                        signed_headers=tuple(verdict_row.signed_headers or ()),
                        failure_reason=verdict_row.failure_reason,
                    ),
                )
            )
    verdicts.sort(key=lambda pair: pair[0])
    return documents, verdicts


def _to_fact(row: db.FactRow) -> Fact:
    return Fact(
        account_id=row.account_id,
        document_sha256=_document_sha(row),
        as_of=row.as_of,
        kind=FactKind(row.kind),
        tier=Tier.from_slug(row.tier),
        currency=row.currency,
        instrument=row.instrument,
        quantity=row.quantity,
        price=row.price,
        amount_minor=row.amount_minor,
        extractor_version=row.extractor_version,
        note=row.note,
    )


def _document_sha(row: db.FactRow) -> str:
    session = Session.object_session(row)
    if session is None:  # pragma: no cover - detached rows are a caller error
        raise RuntimeError("fact row is not attached to a session")
    document = session.get(db.Document, row.document_id)
    return document.sha256 if document else row.document_id


def _account_for(
    session: Session,
    *,
    entity_id: str,
    institution_id: str,
    external_ref: str | None,
    currency: str,
) -> db.Account:
    query = select(db.Account).where(
        db.Account.entity_id == entity_id,
        db.Account.institution_id == institution_id,
        db.Account.external_ref == external_ref,
    )
    account = session.scalar(query)
    if account is None:
        account = db.Account(
            entity_id=entity_id,
            institution_id=institution_id,
            external_ref=external_ref,
            currency=currency,
        )
        session.add(account)
        session.flush()
    return account


def _document_tier(session: Session, document_id: str) -> str:
    tier = session.scalar(
        select(db.FactRow.tier).where(db.FactRow.document_id == document_id).limit(1)
    )
    return tier or Tier.SELF_REPORTED.slug


def _document_verified(session: Session, document_id: str) -> bool:
    return bool(
        session.scalar(
            select(db.DkimVerdictRow.verified).where(
                db.DkimVerdictRow.document_id == document_id
            )
        )
    )


def _jsonable(value):
    """JSON columns cannot hold Decimals or dates; canonical strings can."""
    from datetime import date as _date
    from decimal import Decimal

    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, Decimal):
        from core.canonical import canonical_decimal

        return canonical_decimal(value)
    if isinstance(value, (_date, datetime)):
        return value.isoformat()
    return value
