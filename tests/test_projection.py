"""The fence.

For every disclosure profile, assert the serialized response contains no field
the profile forbids. Deliberately tested against the wire payload rather than
the component: a UI that merely declines to render a field has still sent it,
and anyone can open the network tab.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from adapters import db
from adapters.chain import record_key
from api.app import app, token_hash
from api.projection import Profile
from core.metrics import Config, TWO_AND_TWENTY
from core.types import Channel
from worker import pipeline

# Things that must not appear in a payload that is not allowed to carry them.
# Matched as substrings of the raw JSON, so a nested occurrence anywhere counts.
FORBIDDEN: dict[Profile, tuple[str, ...]] = {
    Profile.SUMMARY: (
        "sharpe", "sortino", "calmar", "max_drawdown", "volatility_annualized",
        "var_historical", "nav_series", "positions", "evidence", "dns_txt_record",
        "merkle_leaves", "findings",
    ),
    Profile.RATIOS_AND_RISK: (
        "nav_series", "positions", "evidence", "dns_txt_record", "merkle_leaves",
    ),
    Profile.FULL_DETAIL: ("positions",),
    Profile.FULL_PLUS_POSITIONS: (),
}


@pytest.fixture()
def seeded(session, corpus):
    entity = db.Entity(name="Fence Fund")
    session.add(entity)
    session.flush()
    record = db.Record(
        entity_id=entity.id,
        slug="fence-fund",
        name="Fence Fund",
        chain_key=record_key("fence-fund"),
        viewer_salt="salt",
    )
    session.add(record)
    session.flush()

    for fixture in corpus.fixtures:
        if fixture.name.startswith("statement-"):
            pipeline.ingest(
                session,
                entity_id=entity.id,
                record_id=record.id,
                raw=fixture.raw,
                channel=Channel.EML_UPLOAD,
                filename=fixture.filename,
            )
    confirmation = corpus.by_name("trade-confirmation")
    pipeline.ingest(
        session,
        entity_id=entity.id,
        record_id=record.id,
        raw=confirmation.raw,
        channel=Channel.EML_UPLOAD,
        filename=confirmation.filename,
    )
    session.flush()
    pipeline.rebuild(
        session, record_id=record.id, config=Config(fee_model=TWO_AND_TWENTY), anchor=False
    )
    session.commit()
    return record


def invite_for(session, record, profile: Profile, token: str) -> str:
    from datetime import datetime, timedelta, timezone

    session.add(
        db.Invite(
            record_id=record.id,
            viewer_email=f"{profile.slug}@example.com",
            profile=profile.slug,
            token_hash=token_hash(token),
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
    )
    session.commit()
    return token


@pytest.mark.parametrize("profile", list(Profile))
def test_forbidden_fields_never_reach_the_wire(session, seeded, profile):
    token = invite_for(session, seeded, profile, f"tok-{profile.slug}")
    client = TestClient(app)

    client.post(f"/api/view/{token}/nda", json={"accept": True})
    response = client.get(f"/api/view/{token}")
    assert response.status_code == 200

    body = response.text
    for forbidden in FORBIDDEN[profile]:
        assert forbidden not in body, (
            f"{profile.slug} leaked {forbidden!r} into the serialized payload"
        )


def test_nothing_at_all_is_served_before_the_nda(session, seeded):
    token = invite_for(session, seeded, Profile.FULL_DETAIL, "tok-gate")
    client = TestClient(app)

    body = client.get(f"/api/view/{token}").text
    payload = json.loads(body)
    assert payload["state"] == "nda_required"
    # Not filtered downstream — never assembled.
    for forbidden in ("metrics", "tier", "snapshot", "twr", "evidence"):
        assert forbidden not in body


def test_consent_is_recorded_before_data_is_served(session, seeded):
    token = invite_for(session, seeded, Profile.SUMMARY, "tok-consent")
    client = TestClient(app)

    assert session.query(db.AccessEvent).count() == 0
    client.post(f"/api/view/{token}/nda", json={"accept": True})
    session.expire_all()
    events = session.query(db.AccessEvent).all()
    assert any(event.action == "nda_accepted" for event in events)


def test_summary_profile_cannot_reach_proofs_or_documents(session, seeded):
    token = invite_for(session, seeded, Profile.SUMMARY, "tok-summary-deny")
    client = TestClient(app)
    client.post(f"/api/view/{token}/nda", json={"accept": True})

    assert client.get(f"/api/view/{token}/bundle").status_code == 403
    assert client.get(f"/api/view/{token}/proof/{'00' * 32}").status_code == 403


def test_a_revoked_invite_stops_working(session, seeded):
    from datetime import datetime, timezone

    token = invite_for(session, seeded, Profile.FULL_DETAIL, "tok-revoke")
    client = TestClient(app)
    client.post(f"/api/view/{token}/nda", json={"accept": True})
    assert client.get(f"/api/view/{token}").status_code == 200

    invite = session.query(db.Invite).filter_by(token_hash=token_hash(token)).one()
    invite.revoked_at = datetime.now(timezone.utc)
    session.commit()

    assert client.get(f"/api/view/{token}").status_code == 403


def test_an_expired_invite_stops_working(session, seeded):
    from datetime import datetime, timedelta, timezone

    token = invite_for(session, seeded, Profile.FULL_DETAIL, "tok-expire")
    invite = session.query(db.Invite).filter_by(token_hash=token_hash(token)).one()
    invite.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    session.commit()

    assert TestClient(app).get(f"/api/view/{token}").status_code == 403


def test_only_the_hash_of_a_token_is_stored(session, seeded):
    token = invite_for(session, seeded, Profile.SUMMARY, "tok-secret-value")
    rows = session.query(db.Invite).all()
    # A leaked database should not hand anyone a working key.
    assert all(token not in (row.token_hash or "") for row in rows)
