"""Stage the demo.

The audience should see the magic, not the typing. This builds three records
that each make one argument, and prints the invite links so the demo starts on a
loaded page instead of an empty form.

    meridian-global-macro  twelve signed months. Source-signed throughout.
    northwind-partners     eleven signed months and one typed into a spreadsheet.
                           Every metric drops to self-reported. One row does it.
    evidence-lab           the five ways DKIM breaks, each with a real signature
                           and a real verdict.
"""

from __future__ import annotations

import argparse
from datetime import date
from decimal import Decimal

from sqlalchemy import delete, select

from adapters import db
from adapters.chain import record_key
from adapters.config import settings
from core.metrics import Config, TWO_AND_TWENTY
from core.types import Channel
from demo.corpus import load_or_build
from worker import pipeline

MERIDIAN = "meridian-global-macro"
NORTHWIND = "northwind-partners"
EVIDENCE_LAB = "evidence-lab"

# The row that costs Northwind its grade. Deliberately the most recent month,
# because that is the one a manager is most likely to be missing when a
# deadline lands.
SELF_REPORTED_CSV = b"""as_of,nav,currency
2026-07-31,15488330.00,USD
"""


def _record(session, slug: str, name: str, strategy: str) -> db.Record:
    existing = session.scalar(select(db.Record).where(db.Record.slug == slug))
    if existing is not None:
        return existing
    entity = db.Entity(name=name)
    session.add(entity)
    session.flush()
    record = db.Record(
        entity_id=entity.id,
        slug=slug,
        name=name,
        strategy=strategy,
        chain_key=record_key(slug),
        viewer_salt=f"salt-{slug}",
    )
    session.add(record)
    session.flush()
    return record


def _invite(session, record: db.Record, email: str, profile: str, token: str) -> str:
    """Deterministic tokens so the demo links survive a reseed.

    Fine here and nowhere else: these records are synthetic. Real invites get
    `secrets.token_urlsafe` in the API, and only the hash is ever stored.
    """
    from api.app import token_hash
    from datetime import datetime, timedelta, timezone

    digest = token_hash(token)
    existing = session.scalar(select(db.Invite).where(db.Invite.token_hash == digest))
    if existing is None:
        session.add(
            db.Invite(
                record_id=record.id,
                viewer_email=email,
                profile=profile,
                token_hash=digest,
                expires_at=datetime.now(timezone.utc) + timedelta(days=365),
            )
        )
        session.flush()
    return token


def seed(*, reset: bool = False, anchor: bool | None = None) -> dict[str, str]:
    corpus = load_or_build(settings().fixture_dir)
    pipeline.set_fixture_dns(corpus.captured_dns)

    db.create_all()
    should_anchor = settings().anchoring_enabled if anchor is None else anchor

    session = db.SessionLocal()
    try:
        if reset:
            for table in (
                db.Anchor, db.MetricRow, db.FindingRow, db.Snapshot, db.FactRow,
                db.ExtractionRow, db.DkimVerdictRow, db.AccessEvent, db.Invite,
                db.Document, db.Account, db.Record, db.Entity,
            ):
                session.execute(delete(table))
            session.commit()

        meridian = _record(
            session, MERIDIAN, "Meridian Global Macro",
            "Discretionary global macro, USD",
        )
        northwind = _record(
            session, NORTHWIND, "Northwind Partners",
            "Same numbers, one month short of proof",
        )
        lab = _record(
            session, EVIDENCE_LAB, "Evidence Lab",
            "Five ways a signature fails, each with a real verdict",
        )

        statements = [f for f in corpus.fixtures if f.name.startswith("statement-")]
        confirmation = corpus.by_name("trade-confirmation")

        def load(record: db.Record, raw: bytes, filename: str, channel=Channel.EML_UPLOAD):
            return pipeline.ingest(
                session,
                entity_id=record.entity_id,
                record_id=record.id,
                raw=raw,
                channel=channel,
                filename=filename,
            )

        changed: dict[str, bool] = {}

        # 1. Twelve signed months plus a signed trade confirmation.
        outcomes = [load(meridian, f.raw, f.filename) for f in statements]
        outcomes.append(load(meridian, confirmation.raw, confirmation.filename))
        changed[meridian.id] = any(not o.duplicate for o in outcomes)

        # 2. The same fund, with the last month typed instead of signed.
        outcomes = [load(northwind, f.raw, f.filename) for f in statements[:-1]]
        outcomes.append(
            load(northwind, SELF_REPORTED_CSV, "july-nav.csv", Channel.CSV_UPLOAD)
        )
        changed[northwind.id] = any(not o.duplicate for o in outcomes)

        # 3. The failure modes, kept in their own record so they grade
        #    themselves rather than dragging a real one down.
        outcomes = [
            load(lab, corpus.by_name(name).raw, corpus.by_name(name).filename)
            for name in (
                "archived-retired-selector",
                "l-tag-appended",
                "tampered-body",
                "forwarded-broken",
                "unknown-domain",
            )
        ]
        changed[lab.id] = any(not o.duplicate for o in outcomes)

        session.commit()

        config = Config(fee_model=TWO_AND_TWENTY)
        for record in (meridian, northwind, lab):
            existing = session.scalar(
                select(db.Snapshot).where(db.Snapshot.record_id == record.id).limit(1)
            )
            # A redeploy re-runs this script. Rebuilding regardless would stack
            # a fresh snapshot and a fresh anchor every deploy, which would put
            # gaps-free but meaningless entries in the very sequence that is
            # supposed to mean something.
            if existing is not None and not changed[record.id]:
                print(f"  {record.slug:24} unchanged, leaving snapshot {existing.seq} alone")
                continue

            outcome = pipeline.rebuild(
                session, record_id=record.id, config=config, anchor=should_anchor
            )
            print(
                f"  {record.slug:24} seq={outcome.snapshot.seq} "
                f"tier={outcome.snapshot.tier.slug:20} "
                f"root={outcome.snapshot.root_hex[:18]}… "
                f"metrics={len(outcome.metrics)} findings={len(outcome.findings)} "
                f"anchor={outcome.anchor_status}"
            )
        session.commit()

        tokens = {
            MERIDIAN: _invite(
                session, meridian, "allocator@example-endowment.org",
                "full_detail", "demo-meridian-full",
            ),
            NORTHWIND: _invite(
                session, northwind, "allocator@example-endowment.org",
                "full_detail", "demo-northwind-full",
            ),
            EVIDENCE_LAB: _invite(
                session, lab, "allocator@example-endowment.org",
                "full_detail", "demo-evidence-lab",
            ),
            f"{MERIDIAN}-summary": _invite(
                session, meridian, "cautious@example-fund.com",
                "summary", "demo-meridian-summary",
            ),
        }
        session.commit()
        return tokens
    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the PodShop Arena demo.")
    parser.add_argument("--reset", action="store_true", help="wipe existing rows first")
    parser.add_argument(
        "--no-anchor", action="store_true", help="skip the on-chain anchor"
    )
    args = parser.parse_args()

    print("seeding…")
    tokens = seed(reset=args.reset, anchor=False if args.no_anchor else None)

    base = settings().public_base_url.rstrip("/")
    print("\ndemo links:")
    for label, token in tokens.items():
        print(f"  {label:34} {base}/view/{token}")
    print(
        "\nEvery message above is synthetic and signed by a key generated at build "
        "time.\nThe cryptography is real; the broker is not."
    )


if __name__ == "__main__":
    main()
