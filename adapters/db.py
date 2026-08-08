"""Persistence.

Two rules from the plan are enforced here rather than hoped for:

Money is `BIGINT` minor units plus a currency code. There is no float column in
this schema and there never will be, because a metric computed from a float NAV
would hash differently on different machines and break the anchor.

`document` and `access_event` are append-only, by convention *and* by a database
trigger that rejects UPDATE and DELETE. An audit trail you can quietly edit is
not an audit trail.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from adapters.config import settings

# JSONB where we have it, plain JSON elsewhere, so a laptop running SQLite and
# Render running Postgres share one set of models.
JSONType = JSON().with_variant(JSONB(), "postgresql")

# Quantity and price are exact decimals, not floats. 12 places matches the
# canonical serializer's scale, so a round-trip through the database cannot
# change a hash.
EXACT = Numeric(38, 12, asdecimal=True)


def _uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime | None) -> datetime | None:
    """Re-attach the timezone a driver dropped.

    Postgres hands back aware datetimes; SQLite does not, and a naive datetime
    reaching the canonical serializer is a hard error by design — there is no
    correct guess for which timezone it meant. Every datetime is stored as UTC,
    so the fix is to say so on the way out rather than to weaken the serializer.
    """
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


class Base(DeclarativeBase):
    pass


class Entity(Base):
    __tablename__ = "entity"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    accounts: Mapped[list["Account"]] = relationship(back_populates="entity")
    records: Mapped[list["Record"]] = relationship(back_populates="entity")


class Account(Base):
    __tablename__ = "account"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    entity_id: Mapped[str] = mapped_column(ForeignKey("entity.id"))
    institution_id: Mapped[str] = mapped_column(String(64))
    external_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    currency: Mapped[str] = mapped_column(String(5), default="USD")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    entity: Mapped[Entity] = relationship(back_populates="accounts")


class Record(Base):
    """A track record: the thing that gets anchored, shown, and argued about."""

    __tablename__ = "record"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    entity_id: Mapped[str] = mapped_column(ForeignKey("entity.id"))
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    strategy: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # keccak(record slug) — the bytes32 the contract is keyed by
    chain_key: Mapped[str] = mapped_column(String(66))
    viewer_salt: Mapped[str] = mapped_column(String(66), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    entity: Mapped[Entity] = relationship(back_populates="records")
    snapshots: Mapped[list["Snapshot"]] = relationship(back_populates="record")


class Document(Base):
    """Write-once. Enforced by trigger, not by good intentions."""

    __tablename__ = "document"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    entity_id: Mapped[str] = mapped_column(ForeignKey("entity.id"))
    record_id: Mapped[str | None] = mapped_column(
        ForeignKey("record.id"), nullable=True, index=True
    )
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    blob_key: Mapped[str] = mapped_column(String(200))
    byte_length: Mapped[int] = mapped_column(Integer)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    channel: Mapped[str] = mapped_column(String(32))
    institution_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    doc_type: Mapped[str] = mapped_column(String(40), default="unknown")
    filename: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Content-addressing is global in the blob store, where identical bytes
    # genuinely are one object. A *document* is an entity's copy of those bytes,
    # so two funds holding the same file each get their own row and their own
    # verdict rather than silently sharing one.
    __table_args__ = (UniqueConstraint("entity_id", "sha256", name="uq_document_entity_sha"),)


class DkimVerdictRow(Base):
    __tablename__ = "dkim_verdict"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(ForeignKey("document.id"), index=True)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    d_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    selector: Mapped[str | None] = mapped_column(String(120), nullable=True)
    algo: Mapped[str | None] = mapped_column(String(40), nullable=True)
    l_tag_present: Mapped[bool] = mapped_column(Boolean, default=False)
    body_hash_matched: Mapped[bool] = mapped_column(Boolean, default=False)
    # The captured key. This column is the reason anchoring earns its place:
    # once the selector leaves DNS, this is the only way the signature stays
    # checkable, and its hash is committed on-chain.
    dns_txt_record: Mapped[str | None] = mapped_column(Text, nullable=True)
    dns_captured_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    signed_headers: Mapped[dict] = mapped_column(JSONType, default=list)
    signature_summaries: Mapped[dict] = mapped_column(JSONType, default=list)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class ExtractionRow(Base):
    __tablename__ = "extraction"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(ForeignKey("document.id"), index=True)
    extractor_id: Mapped[str] = mapped_column(String(80))
    extractor_version: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))
    payload: Mapped[dict] = mapped_column(JSONType, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FactRow(Base):
    __tablename__ = "fact"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    record_id: Mapped[str] = mapped_column(ForeignKey("record.id"), index=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("account.id"))
    document_id: Mapped[str] = mapped_column(ForeignKey("document.id"))
    as_of: Mapped[date] = mapped_column(Date, index=True)
    kind: Mapped[str] = mapped_column(String(20))
    instrument: Mapped[str | None] = mapped_column(String(80), nullable=True)
    quantity: Mapped[Decimal | None] = mapped_column(EXACT, nullable=True)
    price: Mapped[Decimal | None] = mapped_column(EXACT, nullable=True)
    amount_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    currency: Mapped[str] = mapped_column(String(5))
    tier: Mapped[str] = mapped_column(String(24))
    extractor_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)

    __table_args__ = (Index("ix_fact_record_asof", "record_id", "as_of"),)


class Snapshot(Base):
    __tablename__ = "snapshot"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    record_id: Mapped[str] = mapped_column(ForeignKey("record.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    root: Mapped[str] = mapped_column(String(66))
    metrics_hash: Mapped[str] = mapped_column(String(64))
    methodology_version: Mapped[str] = mapped_column(String(20))
    extractor_versions: Mapped[dict] = mapped_column(JSONType, default=dict)
    tier: Mapped[str] = mapped_column(String(24))
    leaves: Mapped[dict] = mapped_column(JSONType, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    record: Mapped[Record] = relationship(back_populates="snapshots")
    metrics: Mapped[list["MetricRow"]] = relationship(back_populates="snapshot")
    findings: Mapped[list["FindingRow"]] = relationship(back_populates="snapshot")
    anchor: Mapped["Anchor | None"] = relationship(back_populates="snapshot", uselist=False)

    # seq is strictly monotonic per record; a gap is visible on-chain and is
    # how backfilling gets caught.
    __table_args__ = (UniqueConstraint("record_id", "seq", name="uq_snapshot_seq"),)


class MetricRow(Base):
    __tablename__ = "metric_result"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("snapshot.id"), index=True)
    key: Mapped[str] = mapped_column(String(40))
    basis: Mapped[str] = mapped_column(String(10))
    value: Mapped[Decimal] = mapped_column(EXACT)
    unit: Mapped[str] = mapped_column(String(20))
    formula: Mapped[str] = mapped_column(Text)
    inputs: Mapped[dict] = mapped_column(JSONType, default=dict)
    tier: Mapped[str] = mapped_column(String(24))

    snapshot: Mapped[Snapshot] = relationship(back_populates="metrics")


class FindingRow(Base):
    __tablename__ = "finding"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("snapshot.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    severity: Mapped[str] = mapped_column(String(12))
    detail: Mapped[str] = mapped_column(Text)
    as_of: Mapped[date | None] = mapped_column(Date, nullable=True)

    snapshot: Mapped[Snapshot] = relationship(back_populates="findings")


class Anchor(Base):
    __tablename__ = "anchor"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("snapshot.id"), unique=True)
    chain_id: Mapped[int] = mapped_column(Integer)
    root: Mapped[str] = mapped_column(String(66))
    seq: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    tx_hash: Mapped[str | None] = mapped_column(String(66), nullable=True)
    block_number: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    snapshot: Mapped[Snapshot] = relationship(back_populates="anchor")


class Invite(Base):
    """Bound to an identity and a disclosure profile. Single-use, expiring,
    revocable — not a public URL with a long random string in it."""

    __tablename__ = "invite"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    record_id: Mapped[str] = mapped_column(ForeignKey("record.id"), index=True)
    viewer_email: Mapped[str] = mapped_column(String(255))
    profile: Mapped[str] = mapped_column(String(32), default="summary")
    nda_version: Mapped[str] = mapped_column(String(20), default="1.0")
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    nda_accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AccessEvent(Base):
    """Append-only, by trigger."""

    __tablename__ = "access_event"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    invite_id: Mapped[str] = mapped_column(ForeignKey("invite.id"), index=True)
    action: Mapped[str] = mapped_column(String(40))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ua: Mapped[str | None] = mapped_column(String(255), nullable=True)
    detail: Mapped[dict] = mapped_column(JSONType, default=dict)
    chain_tx: Mapped[str | None] = mapped_column(String(66), nullable=True)


APPEND_ONLY_TABLES = ("document", "access_event")


def append_only_sql(table: str) -> tuple[str, str]:
    """Postgres trigger that refuses UPDATE and DELETE on a table."""
    function = f"""
    CREATE OR REPLACE FUNCTION {table}_is_append_only() RETURNS trigger AS $$
    BEGIN
        RAISE EXCEPTION '{table} is append-only: % is not permitted', TG_OP;
    END;
    $$ LANGUAGE plpgsql;
    """
    trigger = f"""
    CREATE TRIGGER {table}_append_only
    BEFORE UPDATE OR DELETE ON {table}
    FOR EACH ROW EXECUTE FUNCTION {table}_is_append_only();
    """
    return function, trigger


def install_append_only_triggers(connection) -> None:
    if connection.dialect.name != "postgresql":
        # SQLite is a local-development convenience only. The guarantee is a
        # Postgres one, and the deployment that holds real evidence runs
        # Postgres — see the note in README.
        return
    for table in APPEND_ONLY_TABLES:
        function, trigger = append_only_sql(table)
        connection.execute(text(function))
        connection.execute(text(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table}"))
        connection.execute(text(trigger))


_engine = None
_Session = None


def database_url():
    """The configured URL, password removed, safe to print in a boot log."""
    return make_url(settings().database_url)


def engine():
    global _engine
    if _engine is None:
        url = database_url()
        kwargs = {"pool_pre_ping": True, "future": True}
        if url.drivername.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
            # SQLite will not create a missing directory. It says "unable to
            # open database file" and leaves you to guess which file it meant —
            # which is exactly what a relative URL copied from a laptop does in
            # a container, where the working directory is /app and there is no
            # /app/var. Create the directory and let the path be the answer.
            if url.database and url.database != ":memory:":
                Path(url.database).expanduser().resolve().parent.mkdir(
                    parents=True, exist_ok=True
                )
        _engine = create_engine(url, **kwargs)
    return _engine


def SessionLocal():
    global _Session
    if _Session is None:
        _Session = sessionmaker(bind=engine(), expire_on_commit=False, future=True)
    return _Session()


def create_all() -> None:
    """Used by tests and the local bootstrap. Render runs Alembic."""
    Base.metadata.create_all(engine())
    with engine().begin() as connection:
        install_append_only_triggers(connection)
