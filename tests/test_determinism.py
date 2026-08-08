"""Same inputs, same bytes, same root.

This is the contract that makes everything else meaningful, so it is the test
that must never be skipped. If it fails, the anchor is committing to something
other than what we think it is.

The golden root below is a hard-coded constant on purpose. Building the same
snapshot twice in one process only proves the code is not obviously random; a
constant checked into the repo proves that a different machine, a different
Python build, and a different day all agree.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone

from core import METHODOLOGY_VERSION
from core.canonical import canonical, sha256_hex
from core.metrics import Config, FeeModel, build_series, compute
from core.snapshot import build_snapshot
from core.tiers import Tier
from core.types import Channel, DkimVerdict, DocType, Document, Fact, FactKind

# A fixed scenario with no generated keys in it, so the expected root is stable
# across machines and runs.
FIXED_NAVS = [
    (date(2026, 1, 31), 100_000_000),
    (date(2026, 2, 28), 104_500_000),
    (date(2026, 3, 31), 99_750_000),
    (date(2026, 4, 30), 108_200_000),
]

GOLDEN_ROOT = "0x0b3b27efe1a6dea1d9d32eed279d375434038bda80d491ebb33bbf991d0838e8"


def fixed_facts() -> list[Fact]:
    facts = [
        Fact(
            account_id="account-1",
            document_sha256=f"{index:064x}",
            as_of=day,
            kind=FactKind.NAV,
            tier=Tier.SOURCE_SIGNED,
            currency="USD",
            amount_minor=minor,
            extractor_version="1.0.0",
        )
        for index, (day, minor) in enumerate(FIXED_NAVS)
    ]
    facts.append(
        Fact(
            account_id="account-1",
            document_sha256=f"{99:064x}",
            as_of=date(2026, 3, 10),
            kind=FactKind.CASH_FLOW,
            tier=Tier.SOURCE_SIGNED,
            currency="USD",
            amount_minor=5_000_000,
            extractor_version="1.0.0",
        )
    )
    return facts


def fixed_documents() -> list[Document]:
    return [
        Document(
            sha256=f"{index:064x}",
            blob_key=f"blob-{index}",
            byte_length=1024 + index,
            received_at=datetime(2026, 5, 1, 9, 0, tzinfo=timezone.utc),
            channel=Channel.EML_UPLOAD,
            institution_id="ibkr",
            doc_type=DocType.STATEMENT,
        )
        for index in range(len(FIXED_NAVS))
    ]


def fixed_verdicts() -> list[tuple[str, DkimVerdict]]:
    return [
        (
            f"{index:064x}",
            DkimVerdict(
                verified=True,
                d_domain="ibkr-demo.podarena.test",
                selector="blitz2026",
                algo="rsa-sha256",
                l_tag_present=False,
                dns_txt_record="v=DKIM1; k=rsa; p=FIXEDKEYFORTESTS",
                dns_captured_at=datetime(2026, 5, 1, 9, 0, tzinfo=timezone.utc),
                body_hash_matched=True,
                signed_headers=("from", "to", "subject", "date"),
            ),
        )
        for index in range(len(FIXED_NAVS))
    ]


def build_once():
    facts = fixed_facts()
    series = build_series(facts)
    metrics = compute(series, Config(fee_model=FeeModel()))
    return build_snapshot(
        record_id="determinism-fixture",
        seq=1,
        documents=fixed_documents(),
        verdicts=fixed_verdicts(),
        facts=facts,
        metrics=metrics,
        methodology_version=METHODOLOGY_VERSION,
        extractor_versions={"ibkr.activity_statement": "1.0.0"},
    )


class TestDeterminism:
    def test_root_matches_the_committed_constant(self):
        """The cross-machine check. A change here is either a bug or a
        deliberate methodology change that must bump a version."""
        assert build_once().root_hex == GOLDEN_ROOT

    def test_two_builds_agree(self):
        assert build_once().root_hex == build_once().root_hex

    def test_metric_values_are_byte_identical(self):
        first = {(m.key, m.basis): m.value for m in build_once_metrics()}
        second = {(m.key, m.basis): m.value for m in build_once_metrics()}
        for key in first:
            assert canonical(first[key]) == canonical(second[key])

    def test_fact_hashes_are_stable(self):
        hashes = [sha256_hex(canonical(f.canonical_form())) for f in fixed_facts()]
        again = [sha256_hex(canonical(f.canonical_form())) for f in fixed_facts()]
        assert hashes == again

    def test_fact_order_does_not_change_the_root(self):
        """Leaves are sorted, so the root depends on the set of evidence and not
        on the order the pipeline happened to emit it."""
        facts = fixed_facts()
        forward = _snapshot_with(facts)
        backward = _snapshot_with(list(reversed(facts)))
        assert forward.root_hex == backward.root_hex

    def test_changing_one_minor_unit_changes_the_root(self):
        facts = fixed_facts()
        facts[0] = replace(facts[0], amount_minor=100_000_001)
        assert _snapshot_with(facts).root_hex != GOLDEN_ROOT

    def test_bumping_an_extractor_version_changes_the_root(self):
        """The metrics leaf commits to the code that did the reading, so fixing
        a parser cannot silently keep the old commitment."""
        facts = fixed_facts()
        series = build_series(facts)
        metrics = compute(series, Config(fee_model=FeeModel()))
        bumped = build_snapshot(
            record_id="determinism-fixture",
            seq=1,
            documents=fixed_documents(),
            verdicts=fixed_verdicts(),
            facts=facts,
            metrics=metrics,
            methodology_version=METHODOLOGY_VERSION,
            extractor_versions={"ibkr.activity_statement": "1.0.1"},
        )
        assert bumped.root_hex != GOLDEN_ROOT

    def test_changing_the_captured_dns_key_changes_the_root(self):
        facts = fixed_facts()
        series = build_series(facts)
        metrics = compute(series, Config(fee_model=FeeModel()))
        verdicts = fixed_verdicts()
        sha, verdict = verdicts[0]
        verdicts[0] = (sha, replace(verdict, dns_txt_record="v=DKIM1; p=DIFFERENT"))
        altered = build_snapshot(
            record_id="determinism-fixture",
            seq=1,
            documents=fixed_documents(),
            verdicts=verdicts,
            facts=facts,
            metrics=metrics,
            methodology_version=METHODOLOGY_VERSION,
            extractor_versions={"ibkr.activity_statement": "1.0.0"},
        )
        assert altered.root_hex != GOLDEN_ROOT


def build_once_metrics():
    return compute(build_series(fixed_facts()), Config(fee_model=FeeModel()))


def _snapshot_with(facts: list[Fact]):
    series = build_series(facts)
    metrics = compute(series, Config(fee_model=FeeModel()))
    return build_snapshot(
        record_id="determinism-fixture",
        seq=1,
        documents=fixed_documents(),
        verdicts=fixed_verdicts(),
        facts=facts,
        metrics=metrics,
        methodology_version=METHODOLOGY_VERSION,
        extractor_versions={"ibkr.activity_statement": "1.0.0"},
    )
