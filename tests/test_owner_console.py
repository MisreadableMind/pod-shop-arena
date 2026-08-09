"""The manager's side, and the credential that opens it.

Two things are worth pinning down here. First, that the demo token is only ever
handed to a browser on an instance running the synthetic corpus — that endpoint
is public, so a mistake there is a published password. Second, that the owner
view goes *through* the projection rather than around it: if the manager's own
console reached into the ORM directly it would drift from what allocators get,
and the drift would be invisible until an allocator noticed.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from adapters.config import settings
from api.app import app, pm_token
from api.projection import Profile

from tests.test_projection import seeded  # noqa: F401  (fixture)


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture()
def admin(monkeypatch):
    """An instance with a token set, so the console has a real door."""
    cfg = settings()
    monkeypatch.setattr(cfg, "admin_token", "test-admin-token", raising=False)
    return "test-admin-token"


def auth(token: str) -> dict[str, str]:
    return {"authorization": f"Bearer {token}"}


class TestDemoCredential:
    def test_offered_only_on_a_fixtures_instance(self, client, admin, monkeypatch):
        assert client.get("/api/config").json()["demo_admin_token"] == admin

        monkeypatch.setattr(settings(), "demo_fixtures", False, raising=False)
        assert client.get("/api/config").json()["demo_admin_token"] is None

    def test_absent_when_no_token_is_configured(self, client, monkeypatch):
        monkeypatch.setattr(settings(), "admin_token", None, raising=False)
        assert client.get("/api/config").json()["demo_admin_token"] is None


class TestOwnerEndpointsAreGuarded:
    @pytest.mark.parametrize(
        "path",
        [
            "/api/records/fence-fund/owner",
            "/api/records/fence-fund/disclosure",
            "/api/records/fence-fund/preview/summary",
            "/api/records/fence-fund/invites",
            "/api/records/fence-fund/access-log",
        ],
    )
    def test_refused_without_the_token(self, client, seeded, admin, path):
        assert client.get(path).status_code == 401
        assert client.get(path, headers=auth("wrong")).status_code == 401
        assert client.get(path, headers=auth(admin)).status_code == 200


class TestDisclosureMatrix:
    def test_every_rung_is_measured(self, client, seeded, admin):
        body = client.get(
            "/api/records/fence-fund/disclosure", headers=auth(admin)
        ).json()
        rungs = {rung["profile"]: rung for rung in body["profiles"]}
        assert set(rungs) == {profile.slug for profile in Profile}

        # The matrix is only honest if the numbers move in one direction.
        sizes = [rungs[profile.slug]["bytes"] for profile in Profile]
        assert sizes == sorted(sizes), "a wider profile shipped fewer bytes"

    def test_narrow_rungs_are_missing_the_keys_they_forbid(self, client, seeded, admin):
        body = client.get(
            "/api/records/fence-fund/disclosure", headers=auth(admin)
        ).json()
        rungs = {rung["profile"]: rung for rung in body["profiles"]}

        assert "positions" not in rungs["full_detail"]["keys"]
        assert "positions" in rungs["full_plus_positions"]["keys"]
        for absent in ("evidence", "nav_series", "merkle_leaves", "findings"):
            assert absent not in rungs["summary"]["keys"]

    def test_counts_match_what_the_preview_actually_returns(self, client, seeded, admin):
        """The matrix is a claim about the payload. Check it against the payload."""
        matrix = client.get(
            "/api/records/fence-fund/disclosure", headers=auth(admin)
        ).json()
        for rung in matrix["profiles"]:
            payload = client.get(
                f"/api/records/fence-fund/preview/{rung['profile']}", headers=auth(admin)
            ).json()
            assert len(payload["metrics"]) == rung["counts"]["metrics"]
            assert len(payload.get("evidence", [])) == rung["counts"]["evidence"]
            assert len(payload.get("positions", [])) == rung["counts"]["positions"]

    def test_unknown_profile_is_refused(self, client, seeded, admin):
        response = client.get(
            "/api/records/fence-fund/preview/everything", headers=auth(admin)
        )
        assert response.status_code == 422


class TestOwnerView:
    def test_owner_sees_the_widest_projection(self, client, seeded, admin):
        payload = client.get(
            "/api/records/fence-fund/owner", headers=auth(admin)
        ).json()
        assert payload["state"] == "owner"
        assert payload["profile"] == "full_plus_positions"
        for section in ("metrics", "evidence", "nav_series", "merkle_leaves"):
            assert section in payload

    def test_owner_view_carries_no_watermark(self, client, seeded, admin):
        """The watermark identifies a viewer under NDA. The manager is not one."""
        payload = client.get(
            "/api/records/fence-fund/owner", headers=auth(admin)
        ).json()
        assert "watermark" not in payload

    def test_previewing_does_not_write_an_access_event(self, session, client, seeded, admin):
        """Previewing is the manager looking at their own record. Logging it as
        an allocator view would put a fiction in an append-only log."""
        from adapters import db

        before = session.query(db.AccessEvent).count()
        client.get("/api/records/fence-fund/preview/full_detail", headers=auth(admin))
        session.expire_all()
        assert session.query(db.AccessEvent).count() == before


class TestInviteList:
    def test_lists_status_and_never_the_token(self, session, client, seeded, admin):
        from tests.test_projection import invite_for

        invite_for(session, seeded, Profile.SUMMARY, "tok-owner-list")
        rows = client.get(
            "/api/records/fence-fund/invites", headers=auth(admin)
        ).json()

        assert len(rows) == 1
        assert rows[0]["status"] == "active"
        assert rows[0]["profile"] == "summary"
        # Only the hash was ever stored, so there is nothing here to leak.
        assert "tok-owner-list" not in str(rows)
        assert "token" not in rows[0]

    def test_revoked_invite_reads_as_revoked(self, session, client, seeded, admin):
        from tests.test_projection import invite_for

        invite_for(session, seeded, Profile.SUMMARY, "tok-owner-revoke")
        rows = client.get(
            "/api/records/fence-fund/invites", headers=auth(admin)
        ).json()
        client.post(f"/api/invites/{rows[0]['id']}/revoke", headers=auth(admin))

        after = client.get(
            "/api/records/fence-fund/invites", headers=auth(admin)
        ).json()
        assert after[0]["status"] == "revoked"
        # And the link stops opening, which is the point of the button.
        assert client.get("/api/view/tok-owner-revoke").status_code == 403


class TestSeats:
    """Fund and portfolio manager are two seats, not one with a nicer label.

    The interesting case is the negative one: a PM holding a perfectly valid
    token must not be able to read the pod next door, and must not be able to
    learn it exists. Everything else in the console is a consequence of that.
    """

    def test_a_pm_token_opens_its_own_pod(self, client, admin, seeded):  # noqa: F811
        token = pm_token("fence-fund")
        response = client.get("/api/records/fence-fund/owner", headers=auth(token))
        assert response.status_code == 200

    def test_a_pm_cannot_reach_the_pod_next_door(self, client, admin, seeded):  # noqa: F811
        token = pm_token("some-other-pod")
        for path in (
            "/api/records/fence-fund/owner",
            "/api/records/fence-fund/disclosure",
            "/api/records/fence-fund/invites",
            "/api/records/fence-fund/access-log",
            "/api/records/fence-fund/preview/summary",
        ):
            response = client.get(path, headers=auth(token))
            # 404 rather than 403: a refusal that distinguishes "not yours" from
            # "no such thing" leaks the roster one guess at a time.
            assert response.status_code == 404, path

    def test_a_pm_token_is_not_forgeable_from_a_sibling(self, client, admin, seeded):  # noqa: F811
        """Knowing your own token tells you nothing about anyone else's."""
        mine = pm_token("fence-fund")
        forged = mine.replace("fence-fund", "some-other-pod")
        assert client.get("/api/me", headers=auth(forged)).status_code == 401

    def test_the_roster_is_filtered_on_the_server(self, client, admin, seeded):  # noqa: F811
        fund = client.get("/api/me", headers=auth(admin)).json()
        assert fund["role"] == "fund"
        assert any(r["slug"] == "fence-fund" for r in fund["records"])

        pm = client.get("/api/me", headers=auth(pm_token("fence-fund"))).json()
        assert pm["role"] == "pm"
        assert [r["slug"] for r in pm["records"]] == ["fence-fund"]

    def test_only_the_fund_can_take_on_a_new_pod(self, client, admin, seeded):  # noqa: F811
        body = {"slug": "brand-new-pod", "name": "Brand New"}
        assert client.post("/api/records", json=body, headers=auth(pm_token("fence-fund"))).status_code == 403
