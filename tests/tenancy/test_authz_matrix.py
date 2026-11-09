from __future__ import annotations

import itertools
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from groundtruth.platform.api.dependencies import get_store
from groundtruth.platform.audit import service as audit_service
from groundtruth.platform.auth.authz import (
    ORG_ACTION_TABLE,
    PROJECT_CAPABILITY_TABLE,
    AccessContext,
    Action,
    Capability,
    ProjectAccess,
    ProjectLevel,
    get_access_context,
    level_allows,
    org_allows,
    project_level,
    require_org_action,
    require_project,
)
from groundtruth.platform.auth.sessions import COOKIE_NAME, create_session
from groundtruth.platform.config import get_settings
from groundtruth.platform.store.models import (
    AuditEventRow,
    MembershipRow,
    OrganizationRow,
    ProjectGrantRow,
    ProjectRow,
    SessionRow,
    UserRow,
)
from groundtruth.platform.store.sql import SqlEvidenceStore

NOW = datetime(2026, 1, 1, tzinfo=UTC)
ROLES = ("owner", "admin", "member", "viewer")

# Independent literal copy of design spec section 4 (organization table). Do not import
# from the module under test: editing the module table must make these tests fail.
SPEC_ORG: dict[str, tuple[bool, bool, bool, bool]] = {
    # action: (owner, admin, member, viewer)
    "view_org": (True, True, True, True),
    "create_project": (True, True, True, False),
    "edit_project": (True, True, True, False),
    "start_run": (True, True, True, False),
    "manage_members": (True, True, False, False),
    "manage_grants": (True, True, False, False),
    "view_audit": (True, True, False, False),
    "delete_org": (True, False, False, False),
}

# (owning org, audit grant, contribute grant, view grant); EDIT's owner cell is role-gated.
SPEC_PROJECT: dict[str, tuple[bool, bool, bool, bool]] = {
    "overview": (True, True, True, True),
    "series": (True, True, True, True),
    "evidence_full": (True, True, True, False),
    "diagnostics": (True, True, False, False),
    "dossier_export": (True, True, False, False),
    "report_export": (True, True, True, True),
    "edit": (True, False, False, False),
    "field_contribute": (True, False, True, False),
}
LEVELS = ("owner", "audit", "contribute", "view")


def test_spec_literals_cover_every_enum_member() -> None:
    assert set(SPEC_ORG) == {a.value for a in Action}
    assert set(SPEC_PROJECT) == {c.value for c in Capability}
    assert set(LEVELS) == {lv.value for lv in ProjectLevel}


@pytest.mark.parametrize(
    ("role", "action"), list(itertools.product(ROLES, [a.value for a in Action]))
)
def test_org_action_matrix(role: str, action: str) -> None:
    expected = SPEC_ORG[action][ROLES.index(role)]
    assert org_allows(role, Action(action)) is expected
    assert (role in ORG_ACTION_TABLE[Action(action)]) is expected


def test_unknown_role_is_denied() -> None:
    assert not any(org_allows("stranger", a) for a in Action)


@pytest.mark.parametrize(
    ("level", "cap"), list(itertools.product(LEVELS, [c.value for c in Capability]))
)
def test_project_capability_matrix(level: str, cap: str) -> None:
    expected = SPEC_PROJECT[cap][LEVELS.index(level)]
    assert level_allows(ProjectLevel(level), Capability(cap)) is expected
    assert (ProjectLevel(level) in PROJECT_CAPABILITY_TABLE[Capability(cap)]) is expected


# ---------------------------------------------------------------- database-backed tests


class World:
    """Rows inserted directly; users sign in by cookie token."""

    def __init__(self, factory: sessionmaker[Session]) -> None:
        self.factory = factory

    def org(self, slug: str, type_: str = "ngo") -> str:
        oid = str(uuid.uuid4())
        with self.factory() as db:
            db.add(OrganizationRow(id=oid, slug=slug, name=slug, type=type_, created_at=NOW))
            db.commit()
        return oid

    def user(self, email: str) -> tuple[str, str]:
        """Returns (user id, raw session token)."""
        uid = str(uuid.uuid4())
        with self.factory() as db:
            row = UserRow(
                id=uid,
                email=email,
                password_hash="x",
                role="user",
                is_active=True,
                created_at=NOW,
                last_login_at=None,
            )
            db.add(row)
            db.flush()
            token = create_session(db, row, days=1, user_agent=None)
            db.commit()
        return uid, token

    def member(self, user_id: str, org_id: str, role: str) -> None:
        with self.factory() as db:
            db.add(
                MembershipRow(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    organization_id=org_id,
                    role=role,
                    created_at=NOW,
                )
            )
            db.commit()

    def project(self, org_id: str, slug: str) -> str:
        pid = str(uuid.uuid4())
        with self.factory() as db:
            db.add(
                ProjectRow(
                    id=pid,
                    slug=slug,
                    organization_id=org_id,
                    case_id=None,
                    name=slug,
                    country="ZW",
                    ecosystem="forest",
                    intervention="redd",
                    treatment_start_year=2015,
                    boundary_path=None,
                    boundary_sha256=None,
                    data_mode="simulated",
                    reported_funding_amount=None,
                    reported_funding_currency=None,
                    created_by=None,
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
            db.commit()
        return pid

    def grant(self, project_id: str, org_id: str, level: str, revoked: bool = False) -> None:
        with self.factory() as db:
            db.add(
                ProjectGrantRow(
                    id=str(uuid.uuid4()),
                    project_id=project_id,
                    grantee_organization_id=org_id,
                    level=level,
                    granted_by=None,
                    created_at=NOW,
                    revoked_at=NOW if revoked else None,
                )
            )
            db.commit()

    def set_active(self, token: str, org_id: str | None) -> None:
        from groundtruth.platform.auth.sessions import hash_token

        with self.factory() as db:
            row = db.execute(
                select(SessionRow).where(SessionRow.token_hash == hash_token(token))
            ).scalar_one()
            row.active_organization_id = org_id
            db.commit()

    def active_of(self, token: str) -> str | None:
        from groundtruth.platform.auth.sessions import hash_token

        with self.factory() as db:
            return db.execute(
                select(SessionRow.active_organization_id).where(
                    SessionRow.token_hash == hash_token(token)
                )
            ).scalar_one()

    def denied_events(self) -> list[AuditEventRow]:
        with self.factory() as db:
            return list(
                db.execute(
                    select(AuditEventRow).where(AuditEventRow.action == "authz.denied")
                ).scalars()
            )


@pytest.fixture
def world(tenancy_sessions: sessionmaker[Session]) -> World:
    audit_service._denied_last.clear()
    return World(tenancy_sessions)


@pytest.fixture
def app(tenancy_sessions: sessionmaker[Session]) -> FastAPI:
    app = FastAPI()
    app.dependency_overrides[get_store] = lambda: SqlEvidenceStore(tenancy_sessions)

    @app.get("/ctx")
    def ctx_route(ctx: AccessContext = Depends(get_access_context)) -> dict[str, str]:
        return {"org": ctx.org_id, "role": ctx.role, "type": ctx.org_type}

    @app.get("/orgs/{slug}/audit")
    def audit_route(
        ctx: AccessContext = Depends(require_org_action(Action.VIEW_AUDIT)),
    ) -> dict[str, str]:
        return {"org": ctx.org_id}

    @app.get("/projects/{project_id}/diagnostics")
    def diag(access: ProjectAccess = Depends(require_project(Capability.DIAGNOSTICS))) -> Any:
        return {"level": access.level.value, "project": access.project.id}

    @app.get("/projects/{project_id}/overview")
    def overview(access: ProjectAccess = Depends(require_project(Capability.OVERVIEW))) -> Any:
        return {"level": access.level.value}

    @app.post("/projects/{project_id}/edit")
    def edit(access: ProjectAccess = Depends(require_project(Capability.EDIT))) -> Any:
        return {"level": access.level.value}

    return app


@pytest.fixture
def http(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


def as_user(http: TestClient, token: str) -> TestClient:
    http.cookies.clear()
    http.cookies.set(COOKIE_NAME, token)
    return http


def test_auth_required_false_does_not_bypass(
    http: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "auth_required", False)
    http.cookies.clear()
    assert http.get("/ctx").status_code == 401
    assert http.get("/projects/x/overview").status_code == 401


def test_unauthenticated_is_401(http: TestClient, world: World) -> None:
    http.cookies.clear()
    r = http.get("/ctx")
    assert r.status_code == 401 and r.json()["detail"]["code"] == "unauthenticated"
    http.cookies.set(COOKIE_NAME, "not-a-real-token")
    assert http.get("/ctx").status_code == 401


def test_single_membership_becomes_active_and_is_persisted(http: TestClient, world: World) -> None:
    org = world.org("ngo-a")
    uid, token = world.user("a@example.org")
    world.member(uid, org, "member")
    r = as_user(http, token).get("/ctx")
    assert r.status_code == 200 and r.json() == {"org": org, "role": "member", "type": "ngo"}
    assert world.active_of(token) == org


def test_no_or_many_memberships_without_active_is_409(http: TestClient, world: World) -> None:
    uid, token = world.user("a@example.org")
    r = as_user(http, token).get("/ctx")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "no_active_organization"
    world.member(uid, world.org("o1"), "member")
    world.member(uid, world.org("o2"), "member")
    r = as_user(http, token).get("/ctx")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "no_active_organization"
    assert world.active_of(token) is None


def test_stale_active_org_is_rejected(http: TestClient, world: World) -> None:
    org = world.org("ngo-a")
    other = world.org("ngo-b")
    uid, token = world.user("a@example.org")
    world.member(uid, org, "member")
    world.member(uid, other, "member")
    world.set_active(token, org)
    assert as_user(http, token).get("/ctx").status_code == 200
    with world.factory() as db:
        m = db.execute(
            select(MembershipRow).where(MembershipRow.organization_id == org)
        ).scalar_one()
        db.delete(m)
        db.commit()
    r = http.get("/ctx")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "no_active_organization"
    assert world.active_of(token) is None


def test_role_is_rechecked_every_request(http: TestClient, world: World) -> None:
    org = world.org("ngo-a")
    uid, token = world.user("a@example.org")
    world.member(uid, org, "admin")
    assert as_user(http, token).get("/orgs/ngo-a/audit").status_code == 200
    with world.factory() as db:
        m = db.execute(select(MembershipRow)).scalar_one()
        m.role = "viewer"
        db.commit()
    assert http.get("/ctx").json()["role"] == "viewer"
    assert http.get("/orgs/ngo-a/audit").status_code == 403


def test_org_action_slug_mismatch_is_404_and_role_denial_403(
    http: TestClient, world: World
) -> None:
    org = world.org("ngo-a")
    world.org("ngo-b")
    uid, token = world.user("a@example.org")
    world.member(uid, org, "member")
    c = as_user(http, token)
    assert c.get("/orgs/ngo-b/audit").status_code == 404
    r = c.get("/orgs/ngo-a/audit")
    assert r.status_code == 403
    assert len(world.denied_events()) == 1


def test_no_access_returns_404_and_is_audited(http: TestClient, world: World) -> None:
    owner_org = world.org("owner-org")
    other = world.org("other-org", "funder")
    pid = world.project(owner_org, "secret-proj")
    uid, token = world.user("f@example.org")
    world.member(uid, other, "owner")
    c = as_user(http, token)
    existing = c.get(f"/projects/{pid}/overview")
    audit_service._denied_last.clear()
    missing = c.get("/projects/does-not-exist/overview")
    assert existing.status_code == missing.status_code == 404
    assert existing.json() == missing.json()  # no existence leak
    events = world.denied_events()
    assert len(events) == 2
    assert all(
        e.resource_type == "project" and e.outcome == "denied" and e.actor_user_id == uid
        for e in events
    )
    assert all(e.organization_id == other for e in events)
    assert {e.resource_id for e in events} == {pid, None}


def test_project_resolves_by_slug_and_owner_gets_owner_level(
    http: TestClient, world: World
) -> None:
    org = world.org("owner-org")
    pid = world.project(org, "my-proj")
    uid, token = world.user("o@example.org")
    world.member(uid, org, "viewer")
    c = as_user(http, token)
    assert c.get("/projects/my-proj/overview").json() == {"level": "owner"}
    assert c.get(f"/projects/{pid}/overview").json() == {"level": "owner"}
    assert c.get("/projects/my-proj/diagnostics").json()["project"] == pid
    # EDIT needs the role gate too: viewer of the owning org is refused.
    assert c.post("/projects/my-proj/edit").status_code == 403


def test_owner_member_can_edit(http: TestClient, world: World) -> None:
    org = world.org("owner-org")
    world.project(org, "my-proj")
    uid, token = world.user("o@example.org")
    world.member(uid, org, "member")
    assert as_user(http, token).post("/projects/my-proj/edit").status_code == 200


def test_insufficient_level_returns_403(http: TestClient, world: World) -> None:
    owner_org = world.org("owner-org")
    grantee = world.org("ngo-org")
    pid = world.project(owner_org, "proj")
    world.grant(pid, grantee, "contribute")
    uid, token = world.user("n@example.org")
    world.member(uid, grantee, "owner")
    c = as_user(http, token)
    assert c.get("/projects/proj/overview").status_code == 200
    r = c.get("/projects/proj/diagnostics")
    assert r.status_code == 403 and r.json()["detail"]["code"] == "forbidden"
    events = world.denied_events()
    assert len(events) == 1
    assert events[0].resource_type == "project" and events[0].resource_id == pid
    assert events[0].details["reason"] == "level"
    assert c.post("/projects/proj/edit").status_code == 403  # grants never edit


def test_audit_grant_reaches_diagnostics(http: TestClient, world: World) -> None:
    owner_org = world.org("owner-org")
    auditor = world.org("aud-org", "auditor")
    pid = world.project(owner_org, "proj")
    world.grant(pid, auditor, "audit")
    uid, token = world.user("a@example.org")
    world.member(uid, auditor, "viewer")
    assert as_user(http, token).get("/projects/proj/diagnostics").json()["level"] == "audit"


def test_revoked_grant_gives_no_level(
    http: TestClient, world: World, tenancy_sessions: sessionmaker[Session]
) -> None:
    owner_org = world.org("owner-org")
    grantee = world.org("ngo-org")
    pid = world.project(owner_org, "proj")
    world.grant(pid, grantee, "audit", revoked=True)
    uid, token = world.user("n@example.org")
    world.member(uid, grantee, "owner")
    ctx = AccessContext(user_id=uid, org_id=grantee, org_type="ngo", role="owner")
    with tenancy_sessions() as db:
        project = db.get(ProjectRow, pid)
        assert project is not None
        assert project_level(db, ctx, project) is None
        # same org, an active grant would yield its level
        db.execute(
            ProjectGrantRow.__table__.update().values(revoked_at=None)  # type: ignore[attr-defined]
        )
        db.commit()
        assert project_level(db, ctx, project) is ProjectLevel.AUDIT
    with tenancy_sessions() as db:
        db.execute(
            ProjectGrantRow.__table__.update().values(revoked_at=NOW)  # type: ignore[attr-defined]
        )
        db.commit()
    assert as_user(http, token).get("/projects/proj/overview").status_code == 404


def test_active_org_decides_access_not_other_memberships(http: TestClient, world: World) -> None:
    owner_org = world.org("owner-org")
    other = world.org("other-org")
    world.project(owner_org, "proj")
    uid, token = world.user("m@example.org")
    world.member(uid, owner_org, "owner")
    world.member(uid, other, "owner")
    world.set_active(token, other)
    assert as_user(http, token).get("/projects/proj/overview").status_code == 404
    world.set_active(token, owner_org)
    assert http.get("/projects/proj/overview").status_code == 200
