from __future__ import annotations

from datetime import timedelta

import pytest
import sqlalchemy as sa
from authhelpers import ORIGIN, PASSWORD, login, new_client, register
from fastapi.testclient import TestClient

from groundtruth.platform.api.app import app
from groundtruth.platform.api.dependencies import get_store
from groundtruth.platform.auth import deps, passwords
from groundtruth.platform.auth.sessions import hash_token, utcnow
from groundtruth.platform.store.models import SessionRow, UserRow

pytestmark = pytest.mark.usefixtures("_fast_scrypt")

CLAIM = {"text": "The project restored 500 hectares of mangrove."}


def code(response) -> str:
    return response.json()["detail"]["code"]


def test_first_user_is_admin_then_users(client):
    first = register(client, "Admin@Example.org")
    assert first.status_code == 201
    body = first.json()
    assert body["role"] == "admin"
    assert body["email"] == "admin@example.org"
    assert set(body) == {"id", "email", "role", "is_active", "created_at", "last_login_at"}
    second = register(new_client(client), "u@example.org")
    assert second.json()["role"] == "user"


def test_register_rejects_duplicate_and_weak(client):
    assert register(client, "a@example.org").status_code == 201
    dup = register(new_client(client), "A@example.org")
    assert (dup.status_code, code(dup)) == (409, "email_taken")
    weak = register(new_client(client), "b@example.org", "password123")
    assert (weak.status_code, code(weak)) == (422, "weak_password")


def test_cookie_flags(client, settings, monkeypatch):
    response = register(client, "a@example.org")
    header = response.headers["set-cookie"].lower()
    assert "gt_session=" in header
    assert "httponly" in header
    assert "samesite=lax" in header
    assert "path=/" in header
    assert "max-age=604800" in header
    assert "secure" not in header
    monkeypatch.setattr(settings, "auth_cookie_secure", True)
    other = new_client(client)
    r = register(other, "b@example.org")
    assert "secure" in r.headers["set-cookie"].lower()


def test_no_secret_in_responses_or_db(client, sessions):
    r = register(client, "a@example.org")
    token = client.cookies.get("gt_session")
    assert PASSWORD not in r.text and "scrypt" not in r.text and token not in r.text
    with sessions() as db:
        row = db.execute(sa.select(SessionRow)).scalar_one()
        assert row.token_hash == hash_token(token)
        assert token not in {row.token_hash, row.id}


def test_session_lifecycle_and_logout_revokes(client):
    register(client, "a@example.org")
    me = client.get("/auth/me").json()
    assert me["auth_required"] is True
    assert me["user"]["email"] == "a@example.org"
    stolen = dict(client.cookies)
    out = client.post("/auth/logout", headers={"Origin": ORIGIN})
    assert out.status_code == 204
    assert client.get("/auth/me").json()["user"] is None
    # The old cookie is dead server-side, not merely deleted from the browser.
    replay = new_client(client)
    replay.cookies.update(stolen)
    assert replay.get("/auth/me").json()["user"] is None
    # Idempotent.
    assert client.post("/auth/logout", headers={"Origin": ORIGIN}).status_code == 204


def test_expired_and_revoked_sessions_are_rejected(client, sessions):
    register(client, "a@example.org")
    with sessions() as db:
        row = db.execute(sa.select(SessionRow)).scalar_one()
        row.expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    assert client.get("/auth/me").json()["user"] is None
    login(client, "a@example.org")
    with sessions() as db:
        db.execute(sa.update(SessionRow).values(revoked_at=utcnow()))
        db.commit()
    assert client.get("/auth/me").json()["user"] is None


def test_unknown_email_and_wrong_password_are_indistinguishable(client, monkeypatch):
    register(client, "a@example.org")
    calls = []
    real = passwords.verify_password
    monkeypatch.setattr(passwords, "verify_password", lambda p, s: calls.append(1) or real(p, s))
    wrong = login(new_client(client), "a@example.org", "not the password")
    unknown = login(new_client(client), "nobody@example.org", "not the password")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert code(wrong) == "invalid_credentials"
    assert "set-cookie" not in wrong.headers and "set-cookie" not in unknown.headers
    assert len(calls) == 2  # the unknown email still paid for a verification


def test_rate_limit_after_five_failures(client):
    register(client, "a@example.org")
    other = new_client(client)
    for _ in range(5):
        assert login(other, "a@example.org", "wrong password!").status_code == 401
    blocked = login(other, "a@example.org", PASSWORD)
    assert (blocked.status_code, code(blocked)) == (429, "too_many_attempts")
    assert int(blocked.headers["retry-after"]) > 0


def test_inactive_user_cannot_sign_in(client):
    register(client, "admin@example.org")
    other = new_client(client)
    uid = register(other, "u@example.org").json()["id"]
    r = client.patch(f"/auth/users/{uid}", json={"is_active": False}, headers={"Origin": ORIGIN})
    assert r.status_code == 200
    assert other.get("/auth/me").json()["user"] is None  # existing session ended
    assert login(new_client(client), "u@example.org").status_code == 401


def test_change_password_revokes_other_sessions(client):
    register(client, "a@example.org")
    second = new_client(client)
    login(second, "a@example.org")
    bad = client.post(
        "/auth/change-password",
        json={"current_password": "nope nope nope", "new_password": "a brand new secret"},
        headers={"Origin": ORIGIN},
    )
    assert bad.status_code == 401
    ok = client.post(
        "/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "a brand new secret"},
        headers={"Origin": ORIGIN},
    )
    assert ok.status_code == 204
    assert client.get("/auth/me").json()["user"] is not None
    assert second.get("/auth/me").json()["user"] is None
    assert login(new_client(client), "a@example.org").status_code == 401
    assert login(new_client(client), "a@example.org", "a brand new secret").status_code == 200


def test_registration_closed(client, settings, monkeypatch):
    register(client, "admin@example.org")
    monkeypatch.setattr(settings, "auth_allow_registration", False)
    anon = register(new_client(client), "x@example.org")
    assert (anon.status_code, code(anon)) == (403, "registration_closed")
    assert client.get("/auth/me").json()["registration_open"] is False
    # A signed-in admin can still create accounts, and stays signed in as themselves.
    made = register(client, "x@example.org")
    assert made.status_code == 201 and made.json()["role"] == "user"
    assert client.get("/auth/me").json()["user"]["email"] == "admin@example.org"


def test_admin_user_management_and_last_admin_guard(client):
    admin = register(client, "admin@example.org").json()
    user_client = new_client(client)
    user = register(user_client, "u@example.org").json()
    hdr = {"Origin": ORIGIN}
    assert user_client.get("/auth/users").status_code == 403
    assert new_client(client).get("/auth/users").status_code == 401
    assert len(client.get("/auth/users").json()) == 2
    # Sole admin cannot be demoted or deactivated.
    for payload in ({"role": "dev"}, {"is_active": False}):
        r = client.patch(f"/auth/users/{admin['id']}", json=payload, headers=hdr)
        assert (r.status_code, code(r)) == (409, "last_admin")
    assert client.patch("/auth/users/zzz", json={"role": "dev"}, headers=hdr).status_code == 404
    assert (
        client.patch(f"/auth/users/{user['id']}", json={"role": "viewer"}, headers=hdr).status_code
        == 422
    )
    promoted = client.patch(f"/auth/users/{user['id']}", json={"role": "admin"}, headers=hdr)
    assert promoted.json()["role"] == "admin"
    # With a second admin, the first can step down.
    r = client.patch(f"/auth/users/{admin['id']}", json={"role": "user"}, headers=hdr)
    assert r.status_code == 200


def test_admin_endpoints_enforced_even_when_auth_not_required(client, settings, monkeypatch):
    monkeypatch.setattr(settings, "auth_required", False)
    assert client.get("/auth/users").status_code == 401


# --- role gates -----------------------------------------------------------------------------


def test_protected_endpoints_401_without_session(client):
    assert client.post("/claims/analyze", json=CLAIM, headers={"Origin": ORIGIN}).status_code == 401
    for path in ("/jobs", "/jobs/abc/cancel", "/cases/kariba-redd/verify"):
        r = client.post(path, json={}, headers={"Origin": ORIGIN})
        assert (r.status_code, code(r)) == (401, "unauthenticated"), path


def test_user_passes_user_gate(client):
    register(client, "a@example.org")
    assert client.post("/claims/analyze", json=CLAIM, headers={"Origin": ORIGIN}).status_code == 200


@pytest.mark.parametrize(
    ("role", "gate", "allowed"),
    [
        ("user", "user", True),
        ("user", "dev", False),
        ("dev", "user", True),
        ("dev", "dev", True),
        ("dev", "admin", False),
        ("admin", "dev", True),
        ("admin", "admin", True),
    ],
)
def test_role_ranking(client, sessions, role, gate, allowed):
    register(client, "admin@example.org")
    other = new_client(client)
    uid = register(other, "u@example.org").json()["id"]
    with sessions() as db:
        db.get(UserRow, uid).role = role
        db.commit()
    request = type("R", (), {"app": app, "cookies": dict(other.cookies)})()
    dependency = deps.require_role(gate)  # type: ignore[arg-type]
    if allowed:
        assert dependency(request).role == role  # type: ignore[arg-type,union-attr]
    else:
        with pytest.raises(Exception) as exc:
            dependency(request)  # type: ignore[arg-type]
        assert exc.value.status_code == 403  # type: ignore[attr-defined]


def test_auth_not_required_leaves_endpoints_open(client, settings, monkeypatch):
    monkeypatch.setattr(settings, "auth_required", False)
    r = client.post("/claims/analyze", json=CLAIM)
    assert r.status_code == 200
    me = client.get("/auth/me").json()
    assert me["auth_required"] is False and me["user"] is None


def test_no_store_with_auth_required_is_503_not_allow(settings):
    from groundtruth.platform.api.dependencies import reset_store

    reset_store()
    app.dependency_overrides.pop(get_store, None)
    with TestClient(app) as c:
        r = c.post("/claims/analyze", json=CLAIM)
        assert r.status_code == 503
        assert code(r) == "store_not_configured"
        assert c.post("/auth/login", json={"email": "a@b.co", "password": "x"}).status_code == 503


def test_no_store_with_auth_off_still_works(settings, monkeypatch):
    monkeypatch.setattr(settings, "auth_required", False)
    with TestClient(app) as c:
        assert c.post("/claims/analyze", json=CLAIM).status_code == 200
        assert c.get("/auth/me").json() == {
            "auth_required": False,
            "registration_open": False,
            "user": None,
        }


# --- CSRF -----------------------------------------------------------------------------------


def test_csrf_origin_checked_only_for_unsafe_methods_with_cookie(client):
    register(client, "a@example.org")
    evil = {"Origin": "https://evil.example"}
    r = client.post("/claims/analyze", json=CLAIM, headers=evil)
    assert (r.status_code, code(r)) == (403, "csrf_origin_rejected")
    assert client.post("/claims/analyze", json=CLAIM).status_code == 403  # no Origin at all
    ok_referer = client.post("/claims/analyze", json=CLAIM, headers={"Referer": ORIGIN + "/x"})
    assert ok_referer.status_code == 200
    assert client.post("/auth/logout", headers=evil).status_code == 403
    assert client.get("/auth/me", headers=evil).status_code == 200  # safe method
    # No session cookie: nothing to forge, so no origin requirement.
    assert new_client(client).post("/claims/analyze", json=CLAIM, headers=evil).status_code == 401


def test_cors_allows_credentials_for_listed_origin_only(client):
    ok = client.options(
        "/auth/login",
        headers={"Origin": ORIGIN, "Access-Control-Request-Method": "POST"},
    )
    assert ok.headers["access-control-allow-credentials"] == "true"
    assert ok.headers["access-control-allow-origin"] == ORIGIN
    assert "PATCH" in ok.headers["access-control-allow-methods"]
