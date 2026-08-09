"""The pipeline end to end, including the tamper drill from §10."""

from __future__ import annotations

from sqlalchemy import select

from adapters import db
from adapters.chain import record_key
from core.metrics import Config, TWO_AND_TWENTY
from core.tiers import Tier
from core.types import Channel
from worker import pipeline


def make_record(session, slug: str) -> db.Record:
    entity = db.Entity(name=slug)
    session.add(entity)
    session.flush()
    row = db.Record(
        entity_id=entity.id,
        slug=slug,
        name=slug,
        chain_key=record_key(slug),
        viewer_salt="salt",
    )
    session.add(row)
    session.flush()
    return row


def ingest(session, record, fixture, channel=Channel.EML_UPLOAD):
    return pipeline.ingest(
        session,
        entity_id=record.entity_id,
        record_id=record.id,
        raw=fixture.raw if hasattr(fixture, "raw") else fixture,
        channel=channel,
        filename=getattr(fixture, "filename", "upload.bin"),
    )


class TestIngest:
    def test_a_signed_statement_lands_as_source_signed_facts(self, session, record, corpus):
        outcome = ingest(session, record, corpus.by_name("statement-2026-07"))
        assert outcome.verified is True
        assert outcome.tier is Tier.SOURCE_SIGNED
        assert outcome.facts_written >= 1

        facts = session.scalars(select(db.FactRow)).all()
        assert {f.tier for f in facts} == {"source_signed"}

    def test_re_ingesting_identical_bytes_is_a_no_op(self, session, record, corpus):
        first = ingest(session, record, corpus.by_name("statement-2026-07"))
        second = ingest(session, record, corpus.by_name("statement-2026-07"))
        assert second.duplicate is True
        assert second.document_id == first.document_id
        assert session.scalar(select(db.Document).where(db.Document.id == first.document_id))

    def test_the_captured_dns_key_is_stored(self, session, record, corpus):
        """Without this column the whole DKIM story has a two-year shelf life."""
        ingest(session, record, corpus.by_name("statement-2026-07"))
        verdict = session.scalar(select(db.DkimVerdictRow))
        assert verdict.dns_txt_record is not None
        assert "p=" in verdict.dns_txt_record
        assert verdict.dns_captured_at is not None

    def test_a_csv_can_never_reach_source_signed(self, session, record):
        outcome = ingest(
            session,
            record,
            b"as_of,nav,currency\n2026-07-31,15488330.00,USD\n",
            channel=Channel.CSV_UPLOAD,
        )
        assert outcome.tier is Tier.SELF_REPORTED
        assert outcome.facts_written == 1

    def test_an_unverified_document_is_still_parsed(self, session, record, corpus):
        """Refusing to read a tampered document would hide the tamper rather
        than grade it. It parses, and it parses as self-reported."""
        outcome = ingest(session, record, corpus.by_name("tampered-body"))
        assert outcome.verified is False
        assert outcome.tier is Tier.SELF_REPORTED
        assert outcome.extraction_status == "ok"
        assert outcome.facts_written > 0


class TestTamperDrill:
    """Flip a byte in a stored document. The verdict must fail, the tier must
    drop, and the recomputed root must differ from the anchored one."""

    def test_one_flipped_byte_changes_everything(self, session, corpus):
        clean = make_record(session, "clean")
        dirty = make_record(session, "dirty")

        good = ingest(session, clean, corpus.by_name("trade-confirmation"))
        bad = ingest(session, dirty, corpus.by_name("tampered-body"))
        session.flush()

        # 1. the verdict fails
        assert good.verified is True
        assert bad.verified is False

        # 2. the tier drops
        assert good.tier is Tier.SOURCE_SIGNED
        assert bad.tier is Tier.SELF_REPORTED

        # 3. the recomputed root differs
        clean_snapshot = pipeline.rebuild(session, record_id=clean.id, anchor=False)
        dirty_snapshot = pipeline.rebuild(session, record_id=dirty.id, anchor=False)
        assert clean_snapshot.snapshot.root_hex != dirty_snapshot.snapshot.root_hex

        # 4. and the record says so without being asked
        assert dirty_snapshot.snapshot.tier is Tier.SELF_REPORTED
        assert any(f.kind == "weak_evidence" for f in dirty_snapshot.findings)


class TestSnapshot:
    def test_rejected_documents_are_still_committed(self, session, record, corpus):
        """A message we rejected is evidence of the rejection. Dropping it from
        the tree would let us quietly forget having seen it."""
        ingest(session, record, corpus.by_name("statement-2026-06"))
        ingest(session, record, corpus.by_name("statement-2026-07"))
        ingest(session, record, corpus.by_name("l-tag-appended"))
        session.flush()

        outcome = pipeline.rebuild(session, record_id=record.id, anchor=False)
        kinds = [leaf.kind for leaf in outcome.snapshot.leaves]
        assert kinds.count("document") == 3
        assert kinds.count("dkim_verdict") == 3

    def test_sequence_increments_and_never_repeats(self, session, record, corpus):
        for name in ("statement-2026-05", "statement-2026-06", "statement-2026-07"):
            ingest(session, record, corpus.by_name(name))
            session.flush()

        seqs = [
            pipeline.rebuild(session, record_id=record.id, anchor=False).snapshot.seq
            for _ in range(3)
        ]
        assert seqs == [1, 2, 3]

    def test_a_full_record_computes_and_commits(self, session, record, corpus):
        for fixture in corpus.fixtures:
            if fixture.name.startswith("statement-"):
                ingest(session, record, fixture)
        session.flush()

        outcome = pipeline.rebuild(
            session,
            record_id=record.id,
            config=Config(fee_model=TWO_AND_TWENTY),
            anchor=False,
        )
        assert outcome.snapshot.tier is Tier.SOURCE_SIGNED
        assert len(outcome.metrics) > 10
        assert {m.basis for m in outcome.metrics} == {"net", "gross"}
        # No anchoring key is configured in tests, so this degrades rather
        # than breaking.
        assert outcome.anchor_status == "not_attempted"


class TestReconciliation:
    def test_a_missing_month_is_reported_not_hidden(self, session, record, corpus):
        for name in ("statement-2025-08", "statement-2025-09", "statement-2025-10",
                     "statement-2026-01"):
            ingest(session, record, corpus.by_name(name))
        session.flush()

        outcome = pipeline.rebuild(session, record_id=record.id, anchor=False)
        assert any(f.kind == "series_gap" for f in outcome.findings)
