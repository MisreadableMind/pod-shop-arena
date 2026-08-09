"""HTTP surface.

The fence lives here: an invite bound to an identity and a profile, an NDA gate
that writes consent before a single byte of data is served, and a projection
that decides what exists in the response at all.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from adapters import db
from adapters.blobs import blob_store
from adapters.chain import chain_client, record_key, viewer_commitment
from adapters.config import settings
from api.projection import Profile, project
from core.merkle import MerkleTree
from core.tiers import Tier
from core.types import Channel
from worker import pipeline

NDA_VERSION = "1.0"
NDA_TEXT = (
    "The information behind this gate is confidential. By continuing you agree "
    "not to redistribute it, and you accept that your identity and the time of "
    "access are recorded in an append-only log and committed on-chain."
)

app = FastAPI(
    title="PodShop Arena",
    version="0.1.0",
    description="Track records an allocator can verify without trusting us.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def session() -> Session:
    db_session = db.SessionLocal()
    try:
        yield db_session
        db_session.commit()
    except Exception:
        db_session.rollback()
        raise
    finally:
        db_session.close()


SessionDep = Annotated[Session, Depends(session)]


# -- who is asking ----------------------------------------------------------
#
# A pod shop has two people on the inside of the wall, and they are not the same
# person. The **fund** allocates across pods: it sees the whole roster, and it is
# the only party that can add a pod or take one on. A **portfolio manager** runs
# one pod: they see their own track record, hand out their own links, and cannot
# so much as read the name of the pod next door. The **allocator** is outside the
# wall entirely and never gets a token at all — see `/api/view/{token}`.
#
# Collapsing the first two into one "admin" would have been less code and a lie:
# the whole product is about who can see what, and a console that shows a PM the
# fund's roster is the same failure it exists to prevent.


class Principal(BaseModel):
    role: str  # "fund" | "pm"
    record_slug: str | None = None  # set for pm, None for fund
    label: str

    def covers(self, slug: str) -> bool:
        return self.role == "fund" or self.record_slug == slug


def pm_token(slug: str) -> str:
    """A pod's token, derived from the fund's.

    Deterministic on purpose — a reseed or a redeploy has to leave the demo
    links working, and there is no PM-credential table to migrate. The slug
    travels in the clear so the token resolves without a database hit; the MAC
    is what makes it unforgeable. A PM who knows their own token learns nothing
    about the pod next door, because they can't compute its MAC without the
    fund's secret."""
    secret = settings().admin_token or "open-instance"
    mac = hmac.new(secret.encode(), f"pm:{slug}".encode(), hashlib.sha256)
    return f"pm_{slug}_{mac.hexdigest()[:20]}"


def require_principal(authorization: Annotated[str | None, Header()] = None) -> Principal:
    supplied = (authorization or "").removeprefix("Bearer ").strip()
    expected = settings().admin_token

    if expected and secrets.compare_digest(supplied, expected):
        return Principal(role="fund", label="Fund")

    if supplied.startswith("pm_"):
        slug = supplied[3:].rpartition("_")[0]
        if slug and secrets.compare_digest(pm_token(slug), supplied):
            return Principal(role="pm", record_slug=slug, label="Portfolio manager")

    if not expected:
        # No token configured means an open instance. Fine for the fixture
        # demo, refused the moment real evidence is involved.
        if settings().demo_fixtures:
            return Principal(role="fund", label="Fund")
        raise HTTPException(503, "admin token is not configured")

    raise HTTPException(401, "bad admin token")


AdminDep = Annotated[Principal, Depends(require_principal)]


def require_fund(who: AdminDep) -> Principal:
    """Roster-level authority. A PM is not it."""
    if who.role != "fund":
        raise HTTPException(403, "only the fund can do this")
    return who


FundDep = Annotated[Principal, Depends(require_fund)]


def require_scope(slug: str, who: AdminDep) -> Principal:
    """Guards every per-record console route. `slug` comes off the path.

    404, not 403: a PM asking about a pod that isn't theirs shouldn't learn
    whether it exists."""
    if not who.covers(slug):
        raise HTTPException(404, "no such record")
    return who


ScopeDep = Annotated[Principal, Depends(require_scope)]


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# -- public -----------------------------------------------------------------


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "demo_fixtures": settings().demo_fixtures}


@app.get("/api/config")
def config() -> dict[str, Any]:
    """What the browser needs to check our work against a chain we do not run."""
    cfg = settings()
    return {
        "chain_id": cfg.chain_id,
        "rpc_url": cfg.rpc_url,
        "explorer_url": cfg.explorer_url,
        "registry_address": cfg.registry_address,
        "anchoring_enabled": cfg.anchoring_enabled,
        "demo_fixtures": cfg.demo_fixtures,
        "methodology_version": __import__("core").METHODOLOGY_VERSION,
        # The manager console's password, handed to the browser on purpose so a
        # three-minute demo is not three minutes of typing. It is `None` unless
        # this instance is running the synthetic corpus, and an instance holding
        # real evidence cannot run the synthetic corpus. Both halves of that are
        # tested — see tests/test_owner_console.py.
        "demo_admin_token": cfg.admin_token if cfg.demo_fixtures else None,
    }


@app.get("/api/demo-logins")
def demo_logins(db_session: SessionDep) -> list[dict[str, Any]]:
    """One click per role, on a fixtures instance only.

    Same rule as the admin token above: `None` unless this instance is running
    the synthetic corpus, and an instance holding real evidence cannot."""
    if not settings().demo_fixtures:
        return []
    records = db_session.scalars(select(db.Record).order_by(db.Record.created_at)).all()
    logins = [
        {
            "role": "fund",
            "label": "Fund",
            "scope": f"all {len(records)} pods",
            "token": settings().admin_token or "",
        }
    ]
    logins += [
        {
            "role": "pm",
            "label": record.name,
            "scope": "this pod only",
            "token": pm_token(record.slug),
        }
        for record in records
    ]
    return logins


@app.get("/api/me")
def me(db_session: SessionDep, who: AdminDep) -> dict[str, Any]:
    """Who you are and, therefore, what the console is allowed to list.

    The roster is filtered here rather than in the browser. A PM's console does
    not render a list it then hides — the names of the other pods never reach
    their machine."""
    records = db_session.scalars(select(db.Record).order_by(db.Record.created_at)).all()
    mine = [record for record in records if who.covers(record.slug)]
    return {
        "role": who.role,
        "label": who.label,
        "record_slug": who.record_slug,
        "records": [
            {
                "slug": record.slug,
                "name": record.name,
                "strategy": record.strategy,
                "chain_key": record.chain_key,
            }
            for record in mine
        ],
    }


@app.get("/api/records")
def list_records(db_session: SessionDep) -> list[dict[str, Any]]:
    records = db_session.scalars(select(db.Record).order_by(db.Record.created_at)).all()
    return [
        {
            "slug": record.slug,
            "name": record.name,
            "strategy": record.strategy,
            "chain_key": record.chain_key,
        }
        for record in records
    ]


@app.get("/api/records/{slug}/anchors")
def anchors(slug: str, db_session: SessionDep) -> dict[str, Any]:
    """The anchor timeline. Public on purpose — a gap in the sequence is
    evidence, and evidence behind a login is not much use to anyone."""
    record = _record(db_session, slug)
    rows = db_session.scalars(
        select(db.Snapshot)
        .where(db.Snapshot.record_id == record.id)
        .order_by(db.Snapshot.seq)
    ).all()

    timeline = []
    for snapshot in rows:
        anchor = db_session.scalar(
            select(db.Anchor).where(db.Anchor.snapshot_id == snapshot.id)
        )
        timeline.append(
            {
                "seq": snapshot.seq,
                "root": snapshot.root,
                "tier": snapshot.tier,
                "created_at": snapshot.created_at.isoformat(),
                "leaf_count": len(snapshot.leaves or []),
                "anchor": {
                    "status": anchor.status,
                    "tx_hash": anchor.tx_hash,
                    "block_number": anchor.block_number,
                    "explorer_url": settings().explorer_tx(anchor.tx_hash)
                    if anchor.tx_hash
                    else None,
                }
                if anchor
                else None,
            }
        )

    return {
        "record": {"slug": record.slug, "name": record.name},
        "chain_key": record.chain_key,
        "chain_id": settings().chain_id,
        "registry_address": settings().registry_address,
        "snapshots": timeline,
    }


# -- admin ------------------------------------------------------------------


class RecordIn(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,79}$")
    name: str
    strategy: str | None = None
    entity_name: str | None = None


@app.post("/api/records", status_code=201)
def create_record(body: RecordIn, db_session: SessionDep, _: FundDep) -> dict[str, Any]:
    if db_session.scalar(select(db.Record).where(db.Record.slug == body.slug)):
        raise HTTPException(409, f"record {body.slug} already exists")

    entity = db.Entity(name=body.entity_name or body.name)
    db_session.add(entity)
    db_session.flush()

    record = db.Record(
        entity_id=entity.id,
        slug=body.slug,
        name=body.name,
        strategy=body.strategy,
        chain_key=record_key(body.slug),
        viewer_salt=secrets.token_hex(16),
    )
    db_session.add(record)
    db_session.flush()
    return {"slug": record.slug, "id": record.id, "chain_key": record.chain_key}


@app.post("/api/records/{slug}/documents")
async def upload_document(
    slug: str,
    db_session: SessionDep,
    _: ScopeDep,
    file: UploadFile = File(...),
) -> dict[str, Any]:
    """Ingest a raw message.

    The bytes are stored and verified exactly as uploaded. Nothing in this path
    re-serializes the message, because any normalization of line endings would
    silently destroy the signature.
    """
    record = _record(db_session, slug)
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "empty upload")

    outcome = pipeline.ingest(
        db_session,
        entity_id=record.entity_id,
        record_id=record.id,
        raw=raw,
        channel=Channel.EML_UPLOAD,
        filename=file.filename,
    )
    return outcome.as_dict()


@app.post("/api/records/{slug}/rebuild")
def rebuild(slug: str, db_session: SessionDep, _: ScopeDep) -> dict[str, Any]:
    record = _record(db_session, slug)
    outcome = pipeline.rebuild(db_session, record_id=record.id)
    return {
        "seq": outcome.snapshot.seq,
        "root": outcome.snapshot.root_hex,
        "tier": outcome.snapshot.tier.slug,
        "metrics": len(outcome.metrics),
        "findings": len(outcome.findings),
        "anchor_status": outcome.anchor_status,
        "tx_hash": outcome.tx_hash,
        "explorer_url": settings().explorer_tx(outcome.tx_hash)
        if outcome.tx_hash
        else None,
    }


class InviteIn(BaseModel):
    viewer_email: str
    profile: str = "summary"
    expires_in_hours: int = 168


@app.post("/api/records/{slug}/invites", status_code=201)
def create_invite(
    slug: str, body: InviteIn, db_session: SessionDep, _: ScopeDep
) -> dict[str, Any]:
    """Issue a single-use, expiring, revocable invite bound to one identity.

    The token is returned exactly once and only its hash is stored, so a leaked
    database does not hand anyone a working key to a record.
    """
    record = _record(db_session, slug)
    try:
        profile = Profile.from_slug(body.profile)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None

    token = secrets.token_urlsafe(32)
    invite = db.Invite(
        record_id=record.id,
        viewer_email=body.viewer_email,
        profile=profile.slug,
        nda_version=NDA_VERSION,
        token_hash=token_hash(token),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=body.expires_in_hours),
    )
    db_session.add(invite)
    db_session.flush()
    return {
        "token": token,
        "profile": profile.slug,
        "viewer_email": invite.viewer_email,
        "expires_at": invite.expires_at.isoformat(),
        "url": f"{settings().public_base_url.rstrip('/')}/view/{token}",
    }


@app.post("/api/invites/{invite_id}/revoke")
def revoke_invite(
    invite_id: str, db_session: SessionDep, who: AdminDep
) -> dict[str, Any]:
    invite = db_session.get(db.Invite, invite_id)
    if invite is None:
        raise HTTPException(404, "no such invite")
    # The one console route with no slug in the path, so the scope check has to
    # walk from the invite back to the pod that issued it.
    record = db_session.get(db.Record, invite.record_id)
    if record is None or not who.covers(record.slug):
        raise HTTPException(404, "no such invite")
    invite.revoked_at = datetime.now(timezone.utc)
    db_session.flush()
    return {"id": invite.id, "revoked_at": invite.revoked_at.isoformat()}


def _latest_snapshot(db_session: Session, record: db.Record) -> db.Snapshot:
    snapshot = db_session.scalar(
        select(db.Snapshot)
        .where(db.Snapshot.record_id == record.id)
        .order_by(db.Snapshot.seq.desc())
        .limit(1)
    )
    if snapshot is None:
        raise HTTPException(404, "this record has no snapshot yet")
    return snapshot


def _projection_inputs(db_session: Session, record: db.Record) -> dict[str, Any]:
    snapshot = _latest_snapshot(db_session, record)
    return {
        "record": record,
        "snapshot": snapshot,
        "metrics": db_session.scalars(
            select(db.MetricRow).where(db.MetricRow.snapshot_id == snapshot.id)
        ).all(),
        "findings": db_session.scalars(
            select(db.FindingRow).where(db.FindingRow.snapshot_id == snapshot.id)
        ).all(),
        "facts": db_session.scalars(
            select(db.FactRow)
            .where(db.FactRow.record_id == record.id)
            .order_by(db.FactRow.as_of)
        ).all(),
        "documents": _documents(db_session, record.id),
        "anchor": db_session.scalar(
            select(db.Anchor).where(db.Anchor.snapshot_id == snapshot.id)
        ),
    }


@app.get("/api/records/{slug}/owner")
def owner_view(slug: str, db_session: SessionDep, _: ScopeDep) -> dict[str, Any]:
    """The record as the manager who owns it sees it: everything.

    Same `project()` the allocator path uses, at the widest profile and with no
    watermark. Running the owner view through the projection rather than around
    it is the point — if a field is invisible to every profile, it is invisible
    here too, and the manager finds out before an allocator does.
    """
    record = _record(db_session, slug)
    payload = project(
        profile=Profile.FULL_PLUS_POSITIONS,
        **_projection_inputs(db_session, record),
    )
    payload["state"] = "owner"
    return payload


@app.get("/api/records/{slug}/disclosure")
def disclosure_matrix(slug: str, db_session: SessionDep, _: ScopeDep) -> dict[str, Any]:
    """What each profile would actually put on the wire, measured.

    The manager's real question is not "is it hidden in the UI" — it is "did it
    leave the building". So this runs the projection once per profile and
    reports the serialized size and the top-level keys that survived. A section
    missing from `keys` is a section that does not exist in that response.
    """
    record = _record(db_session, slug)
    inputs = _projection_inputs(db_session, record)

    rungs = []
    for profile in Profile:
        payload = project(profile=profile, **inputs)
        body = json.dumps(payload, default=str)
        metrics = sorted({metric["key"] for metric in payload.get("metrics", [])})
        rungs.append(
            {
                "profile": profile.slug,
                "rank": int(profile),
                "bytes": len(body.encode("utf-8")),
                "keys": sorted(payload.keys()),
                "metric_keys": metrics,
                "counts": {
                    "metrics": len(payload.get("metrics", [])),
                    "evidence": len(payload.get("evidence", [])),
                    "findings": len(payload.get("findings", [])),
                    "nav_series": len(payload.get("nav_series", [])),
                    "positions": len(payload.get("positions", [])),
                    "merkle_leaves": len(payload.get("merkle_leaves", []) or []),
                },
            }
        )

    return {
        "record": {"slug": record.slug, "name": record.name},
        "profiles": rungs,
        # Every section any profile can carry, so the console can draw a matrix
        # with a row per section rather than guessing from the widest rung.
        "sections": sorted({key for rung in rungs for key in rung["keys"]}),
    }


@app.get("/api/records/{slug}/preview/{profile}")
def preview_as(
    slug: str, profile: str, db_session: SessionDep, _: ScopeDep
) -> dict[str, Any]:
    """The exact bytes an allocator on this profile would receive.

    Not a mock-up of the allocator view — the same projection, so what the
    manager previews and what the allocator gets cannot drift apart.
    """
    record = _record(db_session, slug)
    try:
        rung = Profile.from_slug(profile)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None

    payload = project(profile=rung, **_projection_inputs(db_session, record))
    payload["state"] = "open"
    payload["viewer_email"] = "preview@owner"
    return payload


@app.get("/api/records/{slug}/invites")
def list_invites(slug: str, db_session: SessionDep, _: ScopeDep) -> list[dict[str, Any]]:
    """Who holds a key to this record, and what it opens.

    The token itself is unrecoverable — only its hash was stored — so this is a
    list of standing permissions, not a list of links to re-send.
    """
    record = _record(db_session, slug)
    invites = db_session.scalars(
        select(db.Invite)
        .where(db.Invite.record_id == record.id)
        .order_by(db.Invite.created_at)
    ).all()
    if not invites:
        return []

    events = db_session.scalars(
        select(db.AccessEvent)
        .where(db.AccessEvent.invite_id.in_([invite.id for invite in invites]))
        .order_by(db.AccessEvent.at)
    ).all()
    views: dict[str, list[db.AccessEvent]] = {}
    for event in events:
        views.setdefault(event.invite_id, []).append(event)

    now = datetime.now(timezone.utc)
    rows = []
    for invite in invites:
        expires = invite.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        seen = views.get(invite.id, [])
        if invite.revoked_at is not None:
            status = "revoked"
        elif expires < now:
            status = "expired"
        else:
            status = "active"
        rows.append(
            {
                "id": invite.id,
                "viewer_email": invite.viewer_email,
                "profile": invite.profile,
                "status": status,
                "nda_accepted_at": invite.nda_accepted_at.isoformat()
                if invite.nda_accepted_at
                else None,
                "expires_at": expires.isoformat(),
                "created_at": invite.created_at.isoformat(),
                "views": len([event for event in seen if event.action == "view"]),
                "last_seen_at": seen[-1].at.isoformat() if seen else None,
            }
        )
    return rows


@app.get("/api/records/{slug}/access-log")
def access_log(slug: str, db_session: SessionDep, _: ScopeDep) -> list[dict[str, Any]]:
    record = _record(db_session, slug)
    invites = db_session.scalars(
        select(db.Invite).where(db.Invite.record_id == record.id)
    ).all()
    by_id = {invite.id: invite for invite in invites}
    if not by_id:
        return []
    events = db_session.scalars(
        select(db.AccessEvent)
        .where(db.AccessEvent.invite_id.in_(list(by_id)))
        .order_by(db.AccessEvent.at)
    ).all()
    return [
        {
            "at": event.at.isoformat(),
            "action": event.action,
            "viewer_email": by_id[event.invite_id].viewer_email,
            "profile": by_id[event.invite_id].profile,
            "ip": event.ip,
            "chain_tx": event.chain_tx,
            "explorer_url": settings().explorer_tx(event.chain_tx)
            if event.chain_tx
            else None,
        }
        for event in events
    ]


# -- the fence --------------------------------------------------------------


def _invite(db_session: Session, token: str) -> db.Invite:
    invite = db_session.scalar(
        select(db.Invite).where(db.Invite.token_hash == token_hash(token))
    )
    if invite is None:
        raise HTTPException(404, "no such invite")
    now = datetime.now(timezone.utc)
    if invite.revoked_at is not None:
        raise HTTPException(403, "this invite has been revoked")
    expires = invite.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < now:
        raise HTTPException(403, "this invite has expired")
    return invite


@app.get("/api/view/{token}")
def view(token: str, request: Request, db_session: SessionDep) -> dict[str, Any]:
    """The NDA gate renders before anything else.

    Until consent is recorded, this returns the terms and the record's name.
    No metric, no tier, no evidence — not filtered out downstream, simply never
    assembled.
    """
    invite = _invite(db_session, token)
    record = db_session.get(db.Record, invite.record_id)
    assert record is not None

    if invite.nda_accepted_at is None:
        return {
            "state": "nda_required",
            "record": {"name": record.name, "slug": record.slug},
            "viewer_email": invite.viewer_email,
            "profile": invite.profile,
            "nda": {"version": NDA_VERSION, "text": NDA_TEXT},
        }

    inputs = _projection_inputs(db_session, record)

    _record_access(db_session, invite, record, "view", request)

    payload = project(
        profile=Profile.from_slug(invite.profile),
        **inputs,
        watermark={
            "viewer": invite.viewer_email,
            "at": datetime.now(timezone.utc).isoformat(),
            "record": record.slug,
        },
    )
    payload["state"] = "open"
    payload["viewer_email"] = invite.viewer_email
    return payload


class NdaIn(BaseModel):
    accept: bool = True


@app.post("/api/view/{token}/nda")
def accept_nda(
    token: str, body: NdaIn, request: Request, db_session: SessionDep
) -> dict[str, Any]:
    """Consent is written before the first byte of data is served."""
    invite = _invite(db_session, token)
    if not body.accept:
        raise HTTPException(400, "the NDA must be accepted to continue")

    record = db_session.get(db.Record, invite.record_id)
    assert record is not None

    if invite.nda_accepted_at is None:
        invite.nda_accepted_at = datetime.now(timezone.utc)
        db_session.flush()

    event = _record_access(db_session, invite, record, "nda_accepted", request)
    return {
        "state": "accepted",
        "at": invite.nda_accepted_at.isoformat(),
        "chain_tx": event.chain_tx,
        "explorer_url": settings().explorer_tx(event.chain_tx) if event.chain_tx else None,
    }


@app.get("/api/view/{token}/proof/{digest}")
def proof(token: str, digest: str, db_session: SessionDep) -> dict[str, Any]:
    """A Merkle path the browser can re-fold on its own.

    Only for leaves the profile permits. Handing over a proof for a position
    leaf would leak the leaf's hash to a viewer who is not allowed to see the
    position, which is a smaller leak than the position itself but still a leak.
    """
    invite = _invite(db_session, token)
    if invite.nda_accepted_at is None:
        raise HTTPException(403, "the NDA has not been accepted")

    profile = Profile.from_slug(invite.profile)
    if profile < Profile.FULL_DETAIL:
        raise HTTPException(403, "this disclosure profile does not include proofs")

    snapshot = db_session.scalar(
        select(db.Snapshot)
        .where(db.Snapshot.record_id == invite.record_id)
        .order_by(db.Snapshot.seq.desc())
        .limit(1)
    )
    if snapshot is None:
        raise HTTPException(404, "no snapshot")

    leaves = [bytes.fromhex(leaf["digest"]) for leaf in snapshot.leaves or []]
    wanted = digest.removeprefix("0x").lower()
    if wanted not in {leaf.hex() for leaf in leaves}:
        raise HTTPException(404, "no such leaf in this snapshot")

    tree = MerkleTree(leaves)
    merkle_proof = tree.proof_for(bytes.fromhex(wanted))
    return {
        "root": "0x" + tree.root.hex(),
        "seq": snapshot.seq,
        **merkle_proof.as_dict(),
    }


@app.get("/api/view/{token}/document/{sha256}")
def download_document(
    token: str, sha256: str, request: Request, db_session: SessionDep
) -> Response:
    """The original signed bytes, so a viewer can run DKIM themselves.

    This is the route that makes our API not the trust path. Whoever holds the
    .eml and the captured DNS record does not need us at all.
    """
    invite = _invite(db_session, token)
    if invite.nda_accepted_at is None:
        raise HTTPException(403, "the NDA has not been accepted")
    if Profile.from_slug(invite.profile) < Profile.FULL_DETAIL:
        raise HTTPException(403, "this disclosure profile does not include documents")

    document = db_session.scalar(
        select(db.Document).where(
            db.Document.sha256 == sha256, db.Document.record_id == invite.record_id
        )
    )
    if document is None:
        raise HTTPException(404, "no such document in this record")

    record = db_session.get(db.Record, invite.record_id)
    assert record is not None
    _record_access(db_session, invite, record, f"download:{sha256[:12]}", request)

    raw = blob_store().get(document.blob_key)
    return Response(
        content=raw,
        media_type="message/rfc822",
        headers={
            "Content-Disposition": f'attachment; filename="{document.sha256[:16]}.eml"'
        },
    )


@app.get("/api/view/{token}/bundle")
def bundle(token: str, request: Request, db_session: SessionDep) -> Response:
    """Everything needed to prove this record without us.

    The .eml files, the DNS keys as captured at first verification, the Merkle
    leaves and proofs, and the contract address. Feed the zip to
    `podarena-verify bundle` and every check runs offline except the on-chain
    root, which you should check against an RPC we do not control.

    Exporting this is the point of the product. A record you can only verify by
    asking us has not been verified.
    """
    import io
    import zipfile

    invite = _invite(db_session, token)
    if invite.nda_accepted_at is None:
        raise HTTPException(403, "the NDA has not been accepted")
    if Profile.from_slug(invite.profile) < Profile.FULL_DETAIL:
        raise HTTPException(403, "this disclosure profile does not include the bundle")

    record = db_session.get(db.Record, invite.record_id)
    assert record is not None
    snapshot = db_session.scalar(
        select(db.Snapshot)
        .where(db.Snapshot.record_id == record.id)
        .order_by(db.Snapshot.seq.desc())
        .limit(1)
    )
    if snapshot is None:
        raise HTTPException(404, "no snapshot to export")

    _record_access(db_session, invite, record, "bundle_export", request)

    documents = _documents(db_session, record.id)
    leaves = snapshot.leaves or []
    tree = MerkleTree([bytes.fromhex(leaf["digest"]) for leaf in leaves])

    captured: dict[str, str] = {}
    manifest_documents: dict[str, Any] = {}
    for document, verdict in documents:
        manifest_documents[document.sha256] = {
            "filename": document.filename,
            "doc_type": document.doc_type,
            "channel": document.channel,
            "dkim_verified": bool(verdict and verdict.verified),
            "d_domain": verdict.d_domain if verdict else None,
            "selector": verdict.selector if verdict else None,
        }
        if verdict and verdict.dns_txt_record and verdict.selector and verdict.d_domain:
            captured[f"{verdict.selector}._domainkey.{verdict.d_domain}"] = (
                verdict.dns_txt_record
            )

    cfg = settings()
    manifest = {
        "generated_by": "PodShop Arena",
        "record": {"slug": record.slug, "name": record.name, "strategy": record.strategy},
        "snapshot": {
            "seq": snapshot.seq,
            "root": snapshot.root,
            "tier": snapshot.tier,
            "metrics_hash": snapshot.metrics_hash,
            "methodology_version": snapshot.methodology_version,
            "extractor_versions": snapshot.extractor_versions,
        },
        "chain": {
            "chain_id": cfg.chain_id,
            "rpc_url": cfg.rpc_url,
            "registry_address": cfg.registry_address,
            "record_key": record.chain_key,
            "explorer_url": cfg.explorer_address(cfg.registry_address)
            if cfg.registry_address
            else None,
        },
        "documents": manifest_documents,
    }

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, indent=2))
        archive.writestr("captured_dns.json", json.dumps(captured, indent=2, sort_keys=True))
        archive.writestr("leaves.json", json.dumps(leaves, indent=2))
        archive.writestr("HOW-TO-VERIFY.txt", _HOW_TO_VERIFY.strip() + "\n")

        for document, _ in documents:
            name = document.filename or f"{document.sha256[:16]}.eml"
            archive.writestr(f"documents/{name}", blob_store().get(document.blob_key))

        for leaf in leaves:
            merkle_proof = tree.proof_for(bytes.fromhex(leaf["digest"]))
            archive.writestr(
                f"proofs/{leaf['digest'][:16]}.json",
                json.dumps(
                    {"root": snapshot.root, "label": leaf["label"], **merkle_proof.as_dict()},
                    indent=2,
                ),
            )

    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{record.slug}-seq{snapshot.seq}.zip"'
            )
        },
    )


_HOW_TO_VERIFY = """
This bundle proves a track record without PodShop Arena being involved.

  1. Check the signatures. Every .eml in documents/ carries the institution's
     own DKIM signature. captured_dns.json holds the public keys exactly as they
     stood in DNS when we first verified them — which matters, because selectors
     get retired and a signature nobody wrote the key down for becomes
     unverifiable.

  2. Check our reading of them. The extractor versions are in manifest.json.
     Open any .eml and confirm the numbers are what we said they were.

  3. Check the tree. proofs/ holds a Merkle path for every leaf. Each one folds
     to the root in manifest.json.

  4. Check the root against the chain. Use any RPC endpoint you like — ours is
     deliberately not in the trust path.

The quickest route:

    pip install podarena          # or clone the repo
    podarena-verify bundle .

If it disagrees with anything PodShop Arena told you, believe this bundle.
"""


def _record_access(
    db_session: Session,
    invite: db.Invite,
    record: db.Record,
    action: str,
    request: Request,
) -> db.AccessEvent:
    """Commit the access on-chain, then write the audit row once.

    The chain call goes first because it has to. `access_event` is append-only
    in Postgres, so the row must arrive complete — filling in `chain_tx`
    afterwards is an UPDATE, and the trigger rejects it.

    That ordering costs less than it looks like it should. `log_access` never
    raises; it catches and returns a failed receipt. So a network blip still
    writes the row, with a null `chain_tx`, and we still know who looked. The
    only thing we give up is a crash during the RPC itself.
    """
    commitment = viewer_commitment(invite.viewer_email, record.viewer_salt)
    receipt = chain_client().log_access(
        record.chain_key, commitment, int(Profile.from_slug(invite.profile))
    )
    event = db.AccessEvent(
        invite_id=invite.id,
        action=action,
        ip=request.client.host if request.client else None,
        ua=request.headers.get("user-agent", "")[:255] or None,
        detail={"profile": invite.profile},
        chain_tx=receipt.tx_hash or None,
    )
    db_session.add(event)
    db_session.flush()
    return event


def _documents(
    db_session: Session, record_id: str
) -> list[tuple[db.Document, db.DkimVerdictRow | None]]:
    documents = db_session.scalars(
        select(db.Document)
        .where(db.Document.record_id == record_id)
        .order_by(db.Document.received_at)
    ).all()
    pairs = []
    for document in documents:
        verdict = db_session.scalar(
            select(db.DkimVerdictRow).where(
                db.DkimVerdictRow.document_id == document.id
            )
        )
        pairs.append((document, verdict))
    return pairs


def _record(db_session: Session, slug: str) -> db.Record:
    record = db_session.scalar(select(db.Record).where(db.Record.slug == slug))
    if record is None:
        raise HTTPException(404, f"no record {slug}")
    return record


# -- static frontend --------------------------------------------------------

WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"

if WEB_DIST.exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        candidate = WEB_DIST / path
        if path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(WEB_DIST / "index.html")
