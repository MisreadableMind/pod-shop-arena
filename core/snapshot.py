"""Building the commitment.

The tree commits to four things at once: the evidence, the proof that the
evidence was signed, our reading of it, and the version of the code that did the
reading. All four, or the commitment is a fig leaf — a root over facts alone
would let us silently change the parser and keep the same story.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from core.canonical import canonical, leaf_hash, sha256_hex
from core.merkle import MerkleProof, MerkleTree
from core.tiers import Tier, min_tier
from core.types import DkimVerdict, Document, Fact, Finding, MetricResult

LEAF_DOCUMENT = "document"
LEAF_DKIM = "dkim_verdict"
LEAF_FACT = "fact"
LEAF_METRICS = "metrics"

LEAF_KINDS = (LEAF_DOCUMENT, LEAF_DKIM, LEAF_FACT, LEAF_METRICS)


@dataclass(frozen=True, slots=True)
class LeafRef:
    """A leaf plus enough context to tell a viewer what it is.

    `ref` is a human-traceable handle (a document hash, a fact hash) so the UI
    can say *which* piece of evidence a proof covers instead of showing 32
    anonymous bytes.
    """

    kind: str
    ref: str
    digest: bytes
    label: str

    def as_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "ref": self.ref,
            "digest": self.digest.hex(),
            "label": self.label,
        }


@dataclass(frozen=True, slots=True)
class Snapshot:
    """An immutable commitment to one state of a track record.

    `seq` is strictly monotonic per record. A gap in the sequence is visible to
    anyone reading the chain, which is what makes backfilling detectable.
    """

    record_id: str
    seq: int
    root: bytes
    metrics_hash: str
    methodology_version: str
    extractor_versions: dict[str, str]
    leaves: tuple[LeafRef, ...]
    tier: Tier
    findings: tuple[Finding, ...] = ()

    @property
    def root_hex(self) -> str:
        return "0x" + self.root.hex()

    def leaf_for(self, digest_hex: str) -> LeafRef | None:
        wanted = digest_hex.removeprefix("0x").lower()
        for leaf in self.leaves:
            if leaf.digest.hex() == wanted:
                return leaf
        return None

    def proof_for(self, digest_hex: str) -> MerkleProof:
        tree = MerkleTree(leaf.digest for leaf in self.leaves)
        wanted = bytes.fromhex(digest_hex.removeprefix("0x"))
        return tree.proof_for(wanted)

    def as_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "seq": self.seq,
            "root": self.root_hex,
            "metrics_hash": self.metrics_hash,
            "methodology_version": self.methodology_version,
            "extractor_versions": dict(sorted(self.extractor_versions.items())),
            "tier": self.tier.slug,
            "leaf_count": len(self.leaves),
        }


def metrics_leaf_payload(
    metrics: Iterable[MetricResult],
    methodology_version: str,
    extractor_versions: dict[str, str],
) -> dict[str, Any]:
    """The metrics leaf commits to the numbers *and* to the code that produced
    them. Bump an extractor version and the root moves, which is the point."""
    return {
        "methodology_version": methodology_version,
        "extractor_versions": dict(sorted(extractor_versions.items())),
        "metrics": [m.canonical_form() for m in sorted(metrics, key=_metric_sort_key)],
    }


def _metric_sort_key(metric: MetricResult) -> tuple[str, str]:
    return (metric.key, metric.basis)


def build_snapshot(
    *,
    record_id: str,
    seq: int,
    documents: Iterable[Document],
    verdicts: Iterable[tuple[str, DkimVerdict]],
    facts: Iterable[Fact],
    metrics: Iterable[MetricResult],
    methodology_version: str,
    extractor_versions: dict[str, str],
    findings: Iterable[Finding] = (),
) -> Snapshot:
    """Fold everything we know into one root. Pure: same inputs, same bytes."""
    documents = list(documents)
    verdicts = list(verdicts)
    facts = list(facts)
    metrics = list(metrics)
    findings = tuple(findings)

    leaves: list[LeafRef] = []

    for doc in documents:
        leaves.append(
            LeafRef(
                kind=LEAF_DOCUMENT,
                ref=doc.sha256,
                digest=leaf_hash(LEAF_DOCUMENT, doc.canonical_form()),
                label=f"{doc.doc_type.value} received via {doc.channel.value}",
            )
        )

    for doc_sha, verdict in verdicts:
        payload = dict(verdict.canonical_form())
        payload["document_sha256"] = doc_sha
        state = "verified" if verdict.verified else "failed"
        leaves.append(
            LeafRef(
                kind=LEAF_DKIM,
                ref=doc_sha,
                digest=leaf_hash(LEAF_DKIM, payload),
                label=f"DKIM {state} for {verdict.d_domain or 'unknown domain'}",
            )
        )

    for fact in facts:
        form = fact.canonical_form()
        digest = leaf_hash(LEAF_FACT, form)
        leaves.append(
            LeafRef(
                kind=LEAF_FACT,
                ref=sha256_hex(canonical(form)),
                digest=digest,
                label=f"{fact.kind.value} {fact.instrument or ''} on {fact.as_of}".strip(),
            )
        )

    metrics_payload = metrics_leaf_payload(
        metrics, methodology_version, extractor_versions
    )
    metrics_hash = sha256_hex(canonical(metrics_payload))
    leaves.append(
        LeafRef(
            kind=LEAF_METRICS,
            ref=metrics_hash,
            digest=leaf_hash(LEAF_METRICS, metrics_payload),
            label=f"{len(metrics)} metrics under methodology {methodology_version}",
        )
    )

    tree = MerkleTree(leaf.digest for leaf in leaves)

    # The snapshot's own tier is the weakest thing in it. If there are no facts
    # at all there is nothing to grade, and min_tier would rightly refuse — so
    # an evidence-free snapshot is self-reported by construction.
    tier = min_tier([f.tier for f in facts]) if facts else Tier.SELF_REPORTED

    return Snapshot(
        record_id=record_id,
        seq=seq,
        root=tree.root,
        metrics_hash=metrics_hash,
        methodology_version=methodology_version,
        extractor_versions=dict(sorted(extractor_versions.items())),
        leaves=tuple(sorted(leaves, key=lambda leaf: leaf.digest)),
        tier=tier,
        findings=findings,
    )
