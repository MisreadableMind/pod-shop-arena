"""Disclosure profiles, applied as a server-side projection.

The response is *built up* from what a profile permits. It is never built in
full and then filtered down, because the filtering version fails open: add a
field to the full object, forget to add it to the deny-list, and it ships to
everyone. Here, a new field is invisible until someone writes the line that
includes it.

That is the one security property to hold absolutely: hidden data does not cross
the wire. Not hidden with CSS, not omitted by a component, not gated on a flag
the client sends — absent from the serialized payload.
"""

from __future__ import annotations

from enum import IntEnum
from typing import Any, Iterable

from adapters import db
from core.tiers import Tier


class Profile(IntEnum):
    """Ordered by how much they reveal, so comparisons read naturally."""

    SUMMARY = 0
    RATIOS_AND_RISK = 1
    FULL_DETAIL = 2
    FULL_PLUS_POSITIONS = 3

    @property
    def slug(self) -> str:
        return self.name.lower()

    @classmethod
    def from_slug(cls, slug: str) -> Profile:
        try:
            return cls[slug.upper()]
        except KeyError:
            raise ValueError(f"unknown disclosure profile: {slug!r}") from None


DEFAULT_PROFILE = Profile.SUMMARY

# Headline performance. What an allocator sees before they have agreed to
# anything.
SUMMARY_METRICS = frozenset({"twr_cumulative", "twr_annualized", "modified_dietz"})

# Risk and ratios. A separate rung because these are what a competitor would
# most like to have, and they are useless without the headline anyway.
RISK_METRICS = frozenset(
    {
        "volatility_annualized",
        "sharpe",
        "sortino",
        "calmar",
        "max_drawdown",
        "var_historical",
    }
)


def permitted_metrics(profile: Profile) -> frozenset[str]:
    if profile is Profile.SUMMARY:
        return SUMMARY_METRICS
    return SUMMARY_METRICS | RISK_METRICS


def project(
    *,
    profile: Profile,
    record: db.Record,
    snapshot: db.Snapshot,
    metrics: Iterable[db.MetricRow],
    findings: Iterable[db.FindingRow],
    facts: Iterable[db.FactRow],
    documents: Iterable[tuple[db.Document, db.DkimVerdictRow | None]],
    anchor: db.Anchor | None,
    watermark: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build exactly what this profile is allowed to see."""
    allowed = permitted_metrics(profile)

    payload: dict[str, Any] = {
        "record": {
            "slug": record.slug,
            "name": record.name,
            "strategy": record.strategy,
            # keccak(slug). Public by construction — it is the key anyone needs
            # to read this record's anchor off the chain without asking us.
            "chain_key": record.chain_key,
        },
        "profile": profile.slug,
        # Nothing is displayed without its tier next to it.
        "tier": snapshot.tier,
        "tier_label": Tier.from_slug(snapshot.tier).label,
        "tier_meaning": Tier.from_slug(snapshot.tier).meaning,
        "snapshot": {
            "seq": snapshot.seq,
            "root": snapshot.root,
            "metrics_hash": snapshot.metrics_hash,
            "methodology_version": snapshot.methodology_version,
            "extractor_versions": snapshot.extractor_versions,
            "created_at": snapshot.created_at.isoformat(),
        },
        "anchor": _anchor(anchor),
        "metrics": [
            _metric(row) for row in metrics if row.key in allowed
        ],
    }

    if watermark is not None:
        payload["watermark"] = watermark

    if profile >= Profile.FULL_DETAIL:
        payload["findings"] = [
            {
                "kind": row.kind,
                "severity": row.severity,
                "detail": row.detail,
                "as_of": row.as_of.isoformat() if row.as_of else None,
            }
            for row in findings
        ]
        payload["evidence"] = [
            _document(document, verdict) for document, verdict in documents
        ]
        payload["nav_series"] = [
            {
                "as_of": fact.as_of.isoformat(),
                "amount_minor": fact.amount_minor,
                "currency": fact.currency,
                "tier": fact.tier,
            }
            for fact in facts
            if fact.kind == "nav"
        ]
        payload["flows"] = [
            {
                "as_of": fact.as_of.isoformat(),
                "amount_minor": fact.amount_minor,
                "currency": fact.currency,
                "tier": fact.tier,
                "note": fact.note,
            }
            for fact in facts
            if fact.kind == "cash_flow"
        ]
        payload["merkle_leaves"] = snapshot.leaves

    if profile >= Profile.FULL_PLUS_POSITIONS:
        # Positions are opt-in, per viewer, every time. This is the rung a
        # manager is most afraid of, and it is the last one for that reason.
        payload["positions"] = [
            {
                "as_of": fact.as_of.isoformat(),
                "kind": fact.kind,
                "instrument": fact.instrument,
                "quantity": str(fact.quantity) if fact.quantity is not None else None,
                "price": str(fact.price) if fact.price is not None else None,
                "amount_minor": fact.amount_minor,
                "currency": fact.currency,
                "tier": fact.tier,
            }
            for fact in facts
            if fact.kind in ("trade", "position")
        ]

    return payload


def _metric(row: db.MetricRow) -> dict[str, Any]:
    return {
        "key": row.key,
        "basis": row.basis,
        "value": str(row.value),
        "unit": row.unit,
        "formula": row.formula,
        "tier": row.tier,
        "inputs": row.inputs,
    }


def _anchor(anchor: db.Anchor | None) -> dict[str, Any] | None:
    if anchor is None:
        return None
    return {
        "status": anchor.status,
        "chain_id": anchor.chain_id,
        "root": anchor.root,
        "seq": anchor.seq,
        "tx_hash": anchor.tx_hash,
        "block_number": anchor.block_number,
        "confirmed_at": anchor.confirmed_at.isoformat() if anchor.confirmed_at else None,
        "error": anchor.error,
    }


def _document(document: db.Document, verdict: db.DkimVerdictRow | None) -> dict[str, Any]:
    """Evidence, with the captured key that keeps it checkable.

    `dns_txt_record` is deliberately included at full detail: a viewer who has
    the .eml and this record can verify the signature themselves, with no
    access to our API and no working DNS. That is the whole point.
    """
    entry: dict[str, Any] = {
        "sha256": document.sha256,
        "filename": document.filename,
        "doc_type": document.doc_type,
        "channel": document.channel,
        "institution_id": document.institution_id,
        "byte_length": document.byte_length,
        "received_at": document.received_at.isoformat(),
    }
    if verdict is not None:
        entry["dkim"] = {
            "verified": verdict.verified,
            "d_domain": verdict.d_domain,
            "selector": verdict.selector,
            "algo": verdict.algo,
            "l_tag_present": verdict.l_tag_present,
            "body_hash_matched": verdict.body_hash_matched,
            "dns_txt_record": verdict.dns_txt_record,
            "dns_captured_at": verdict.dns_captured_at.isoformat()
            if verdict.dns_captured_at
            else None,
            "failure_reason": verdict.failure_reason,
            "signatures": verdict.signature_summaries,
        }
    return entry
