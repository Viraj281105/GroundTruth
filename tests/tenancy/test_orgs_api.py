from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "auth"))
from authhelpers import ORIGIN, new_client, register

from groundtruth.platform.store.models import AuditEventRow, MembershipRow
from groundtruth.platform.tenancy import service as tenancy

pytestmark = pytest.mark.usefixtures("_fast_scrypt")
H = {"Origin": ORIGIN}


def _org(client, name="Demo NGO", type_="ngo"):
    return client.post("/orgs", json={"name": name, "type": type_}, headers=H)


def test_create_org_makes_creator_owner(client, sessions):
    register(client, "a@example.org")
    r = _org(client)
    assert r.status_code == 201
    body = r.json()
    assert body["slug"] == "demo-ngo" and body["role"] == "owner" and body["type"] == "ngo"
    assert _org(client).json()["slug"] == "demo-ngo-2"
    with sessions() as db:
        assert db.execute(select(MembershipRow.role)).scalars().first() == "owner"


def test_cannot_create_reference_org(client):
    register(client, "a@example.org")
    assert _org(client, type_="reference").status_code == 422


def test_slug_is_never_uuid_shaped(client):
    register(client, "a@example.org")
    name = str(uuid.uuid4())
    slug = _org(client, name=name).json()["slug"]
    with pytest.raises(ValueError):
        uuid.UUID(slug)


def test_me_orgs_empty_for_new_user(client):
    register(client, "a@example.org")
    me = client.get("/auth/me").json()
    assert me["organizations"] == [] and me["active_organization"] is None
    assert me["user"]["email"] == "a@example.org"


def test_me_single_membership_becomes_active(client):
    register(client, "a@example.org")
    _org(client)
    me = client.get("/auth/me").json()
    assert me["active_organization"]["slug"] == "demo-ngo"
    assert [o["slug"] for o in me["organizations"]] == ["demo-ngo"]


def test_switch_active_org_requires_membership(client):
    register(client, "a@example.org")
    _org(client)
    other = new_client(client)
    register(other, "b@example.org")
    _org(other, name="Other")
    r = client.post("/orgs/active", json={"slug": "other"}, headers=H)
    assert r.status_code == 404
    unknown = client.post("/orgs/active", json={"slug": "nope"}, headers=H)
    assert unknown.status_code == 404 and unknown.json() == r.json()


def test_switch_active_org_is_audited(client, sessions):
    register(client, "a@example.org")
    _org(client)
    _org(client, name="Second")
    assert client.get("/auth/me").json()["active_organization"] is None
    r = client.post("/orgs/active", json={"slug": "second"}, headers=H)
    assert r.status_code == 200 and r.json()["slug"] == "second"
    assert client.get("/auth/me").json()["active_organization"]["slug"] == "second"
    with sessions() as db:
        actions = db.execute(select(AuditEventRow.action)).scalars().all()
    assert "org.switch" in actions


def test_member_management_and_last_owner(client, sessions):
    register(client, "a@example.org")
    me = _org(client).json()
    other = new_client(client)
    uid = register(other, "b@example.org").json()["id"]
    owner_id = client.get("/auth/me").json()["user"]["id"]
    assert client.post("/orgs/active", json={"slug": "demo-ngo"}, headers=H).status_code == 200
    base = "/orgs/demo-ngo/members"
    assert me["slug"] == "demo-ngo"
    assert (
        client.post(base, json={"email": "b@example.org", "role": "member"}, headers=H).status_code
        == 201
    )
    assert (
        client.post(base, json={"email": "b@example.org", "role": "member"}, headers=H).status_code
        == 409
    )
    members = client.get(base).json()
    assert {m["email"] for m in members} == {"a@example.org", "b@example.org"}
    r = client.patch(f"{base}/{uid}", json={"role": "admin"}, headers=H)
    assert r.status_code == 200 and r.json()["role"] == "admin"
    assert client.delete(f"{base}/{uid}", headers=H).status_code == 204
    assert client.delete(f"{base}/{owner_id}", headers=H).status_code == 409
    assert client.patch(f"{base}/{owner_id}", json={"role": "admin"}, headers=H).status_code == 409
    with sessions() as db:
        actions = set(db.execute(select(AuditEventRow.action)).scalars().all())
    assert {"org.member_add", "org.member_remove", "org.member_role"} <= actions


def test_last_owner_cannot_leave(client, sessions):
    register(client, "a@example.org")
    _org(client)
    uid = client.get("/auth/me").json()["user"]["id"]
    r = client.delete(f"/orgs/demo-ngo/members/{uid}", headers=H)
    assert r.status_code == 409
    with sessions() as db:
        org_id = tenancy.list_user_memberships(db, uid)[0][0].id
        with pytest.raises(tenancy.TenancyConflictError):
            tenancy.remove_member(db, org_id, uid, actor_role="owner")


def test_add_member_unknown_email(client):
    register(client, "a@example.org")
    _org(client)
    r = client.post(
        "/orgs/demo-ngo/members", json={"email": "ghost@example.org", "role": "member"}, headers=H
    )
    assert r.status_code == 404


def test_member_routes_need_active_org_slug(client):
    register(client, "a@example.org")
    _org(client)
    other = new_client(client)
    register(other, "b@example.org")
    _org(other, name="Other")
    assert client.get("/orgs/other/members").status_code == 404


def test_list_orgs(client):
    register(client, "a@example.org")
    _org(client)
    assert [o["slug"] for o in client.get("/orgs").json()] == ["demo-ngo"]


def test_orgs_require_session(client):
    assert client.get("/orgs").status_code == 401


# --- fix round 1: owner-role escalation and check-then-insert races ---------------------


def _team(client):
    """Owner A (client), admin B, member C, second owner D; returns clients and ids."""
    register(client, "a@example.org")
    _org(client)
    clients, ids = {}, {}
    for key in "bcd":
        c = new_client(client)
        ids[key] = register(c, f"{key}@example.org").json()["id"]
        clients[key] = c
    ids["a"] = client.get("/auth/me").json()["user"]["id"]
    base = "/orgs/demo-ngo/members"
    for key, role in (("b", "admin"), ("c", "member"), ("d", "owner")):
        r = client.post(base, json={"email": f"{key}@example.org", "role": role}, headers=H)
        assert r.status_code == 201
    admin = clients["b"]
    assert admin.post("/orgs/active", json={"slug": "demo-ngo"}, headers=H).status_code == 200
    return base, ids, admin


def test_admin_cannot_touch_owner_role(client):
    base, ids, admin = _team(client)
    assert admin.patch(f"{base}/{ids['b']}", json={"role": "owner"}, headers=H).status_code == 403
    assert admin.patch(f"{base}/{ids['c']}", json={"role": "owner"}, headers=H).status_code == 403
    add = admin.post(base, json={"email": "c@example.org", "role": "owner"}, headers=H)
    assert add.status_code == 403
    assert admin.patch(f"{base}/{ids['d']}", json={"role": "member"}, headers=H).status_code == 403
    assert admin.delete(f"{base}/{ids['d']}", headers=H).status_code == 403
    assert admin.delete(f"{base}/{ids['a']}", headers=H).status_code == 403


def test_admin_manages_member_and_viewer(client):
    base, ids, admin = _team(client)
    assert admin.patch(f"{base}/{ids['c']}", json={"role": "viewer"}, headers=H).status_code == 200
    assert admin.patch(f"{base}/{ids['c']}", json={"role": "admin"}, headers=H).status_code == 200
    assert admin.delete(f"{base}/{ids['c']}", headers=H).status_code == 204
    r = admin.post(base, json={"email": "c@example.org", "role": "viewer"}, headers=H)
    assert r.status_code == 201


def test_owner_may_grant_demote_and_remove_owner(client):
    base, ids, _ = _team(client)
    assert client.post("/orgs/active", json={"slug": "demo-ngo"}, headers=H).status_code == 200
    assert client.patch(f"{base}/{ids['c']}", json={"role": "owner"}, headers=H).status_code == 200
    assert client.patch(f"{base}/{ids['d']}", json={"role": "admin"}, headers=H).status_code == 200
    assert client.delete(f"{base}/{ids['c']}", headers=H).status_code == 204
    # ids['a'] is now the only owner: the last-owner guard still applies to an owner.
    assert client.delete(f"{base}/{ids['a']}", headers=H).status_code == 409


def test_create_org_slug_race_retries_with_suffix(client, monkeypatch):
    register(client, "a@example.org")
    assert _org(client).status_code == 201
    real = tenancy._unique_slug
    calls = {"n": 0}

    def stale(db, base):
        calls["n"] += 1
        return "demo-ngo" if calls["n"] == 1 else real(db, base)

    monkeypatch.setattr(tenancy, "_unique_slug", stale)
    r = _org(client)
    assert r.status_code == 201 and r.json()["slug"] == "demo-ngo-2"


def test_add_member_duplicate_race_is_409(client, monkeypatch):
    register(client, "a@example.org")
    _org(client)
    register(new_client(client), "b@example.org")
    base = "/orgs/demo-ngo/members"
    body = {"email": "b@example.org", "role": "member"}
    assert client.post(base, json=body, headers=H).status_code == 201
    monkeypatch.setattr(tenancy, "get_membership", lambda *a, **k: None)
    assert client.post(base, json=body, headers=H).status_code == 409
