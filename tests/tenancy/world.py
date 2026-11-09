"""A seeded multi-tenant world for route-level authorization tests.

Reference org (owner of every YAML case, including private ``mikoko-pamoja``), the four
demo orgs the seed grants Kariba to, and an outsider org with no grant on anything. Helpers
here are test support only: HTTP sign-in goes through the real ``/auth`` routes and every
row is created by the production seed or queue.
"""

from __future__ import annotations

import sys
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "auth"))
from authhelpers import ORIGIN, login, new_client, register

from groundtruth.platform.api.app import app
from groundtruth.platform.api.dependencies import get_jobs, get_store, reset_store
from groundtruth.platform.auth import passwords
from groundtruth.platform.auth.ratelimit import login_limiter
from groundtruth.platform.cases.registry import get_case
from groundtruth.platform.config import get_settings
from groundtruth.platform.jobs.queue import JobQueue
from groundtruth.platform.jobs.service import SqlJobService
from groundtruth.platform.projects.seed import DEMO_DOMAIN, SeedReport, _backfill_project_ids, seed
from groundtruth.platform.store import migrate
from groundtruth.platform.store.database import create_db_engine, create_session_factory
from groundtruth.platform.store.models import (
    AnalysisRunRow,
    JobRow,
    MembershipRow,
    OrganizationRow,
    ProjectRow,
    UserRow,
)
from groundtruth.platform.store.sql import SqlEvidenceStore

CASES = Path(__file__).resolve().parents[2] / "cases"
GRANTED_CASE = "kariba-redd"
"""Owned by Reference; granted to the four demo orgs (ngo contribute, auditor audit, ...)."""
PRIVATE_CASE = "mikoko-pamoja"
"""Owned by Reference; no grant to anyone else."""
OUTSIDER_EMAIL = "outsider@example.org"
REF_EMAIL = "ref@example.org"


@dataclass
class World:
    sessions: sessionmaker[Session]
    clients: dict[str, TestClient]
    user_ids: dict[str, str]
    project_ids: dict[str, str]
    """case_id -> project id, for every seeded case project."""
    org_ids: dict[str, str] = field(default_factory=dict)

    def client(self, who: str) -> TestClient:
        return self.clients[who]


class FilingClient(TestClient):
    """A client that files unfiled runs under their case's project before every request.

    For tests of the pre-tenancy run/job routes, which create runs straight through the queue
    or store with no project. It runs the production seed backfill (``_backfill_project_ids``),
    the same step an operator runs after the migration, so the routes under test see runs as
    they would after a real seed.
    """

    sessions: sessionmaker[Session] | None = None

    def request(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if self.sessions is not None:
            with self.sessions() as db:
                _backfill_project_ids(db, SeedReport())
                db.commit()
        return super().request(*args, **kwargs)


def _browser(client: TestClient, sessions: sessionmaker[Session], backfill: bool) -> TestClient:
    if backfill:
        c: TestClient = FilingClient(app, base_url=ORIGIN)
        c.sessions = sessions  # type: ignore[attr-defined]
    else:
        c = new_client(client)
    c.headers["Origin"] = ORIGIN
    return c


def build_world(
    client: TestClient,
    sessions: sessionmaker[Session],
    *,
    wire_jobs: bool = True,
    backfill: bool = False,
) -> World:
    """Seed, then sign in one HTTP client per persona.

    ``wire_jobs`` points ``get_jobs`` at a job service on ``sessions`` (leave it ``False`` when
    the test installs its own). ``backfill`` makes every persona client a ``FilingClient``.
    """
    with sessions() as db:
        report = seed(db, cases_dir=CASES, demo=True)
        db.commit()
        reference_id = db.execute(
            select(OrganizationRow.id).where(OrganizationRow.slug == "reference")
        ).scalar_one()
        project_ids = dict(
            db.execute(
                select(ProjectRow.case_id, ProjectRow.id).where(ProjectRow.case_id.is_not(None))
            ).all()
        )
    demo_passwords = dict(report.demo_users)
    clients: dict[str, TestClient] = {}
    for key in ("ngo", "funder", "auditor", "government"):
        c = _browser(client, sessions, backfill)
        email = f"{key}@{DEMO_DOMAIN}"
        assert login(c, email, demo_passwords[email]).status_code == 200
        clients[key] = c

    ref = _browser(client, sessions, backfill)
    assert register(ref, REF_EMAIL).status_code in (200, 201)
    outsider = _browser(client, sessions, backfill)
    assert register(outsider, OUTSIDER_EMAIL).status_code in (200, 201)
    assert outsider.post("/orgs", json={"name": "Outsider NGO", "type": "ngo"}).status_code == 201
    clients["ref"], clients["outsider"] = ref, outsider

    with sessions() as db:
        ref_user = db.execute(select(UserRow).where(UserRow.email == REF_EMAIL)).scalar_one()
        db.add(
            MembershipRow(
                id=str(uuid.uuid4()),
                user_id=ref_user.id,
                organization_id=reference_id,
                role="owner",
                created_at=datetime.now(UTC),
            )
        )
        db.commit()
        user_ids = {
            key: db.execute(
                select(UserRow.id).where(
                    UserRow.email
                    == (
                        REF_EMAIL
                        if key == "ref"
                        else OUTSIDER_EMAIL
                        if key == "outsider"
                        else f"{key}@{DEMO_DOMAIN}"
                    )
                )
            ).scalar_one()
            for key in clients
        }
        org_ids = {o.slug: o.id for o in db.execute(select(OrganizationRow)).scalars()}

    if wire_jobs:
        store = SqlEvidenceStore(sessions)
        app.dependency_overrides[get_jobs] = lambda: SqlJobService(store, JobQueue(sessions))
    return World(
        sessions=sessions,
        clients=clients,
        user_ids=user_ids,
        project_ids=project_ids,
        org_ids=org_ids,
    )


def queue_run(
    sessions: sessionmaker[Session],
    case_id: str,
    project_id: str | None,
    *,
    seed_value: int = 1,
    requested_by: str | None = None,
) -> str:
    """A QUEUED simulated run for ``case_id``, filed under ``project_id`` (may be ``None``)."""
    request = get_case(case_id).to_request(data_mode="simulated", seed=seed_value)
    run_id = JobQueue(sessions).submit(request, requested_by=requested_by).run_id
    with sessions() as db:
        db.execute(
            update(AnalysisRunRow)
            .where(AnalysisRunRow.run_id == run_id)
            .values(project_id=project_id)
        )
        db.execute(update(JobRow).where(JobRow.run_id == run_id).values(project_id=project_id))
        db.commit()
    return run_id


def store_completed_run(
    sessions: sessionmaker[Session], result: object, project_id: str | None
) -> str:
    """Persist a finished ``AnalysisResult`` and file it under ``project_id``."""
    store = SqlEvidenceStore(sessions)
    store.save_result(result)  # type: ignore[arg-type]
    run_id: str = result.run_id  # type: ignore[attr-defined]
    with sessions() as db:
        db.execute(
            update(AnalysisRunRow)
            .where(AnalysisRunRow.run_id == run_id)
            .values(project_id=project_id)
        )
        db.commit()
    return run_id


def configure_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings a signed-in HTTP test needs: auth on, plain-HTTP cookies, the test origin."""
    monkeypatch.setattr(passwords, "SCRYPT_N", 2**10)
    settings = get_settings()
    monkeypatch.setattr(settings, "auth_required", True)
    monkeypatch.setattr(settings, "auth_allow_registration", True)
    monkeypatch.setattr(settings, "auth_cookie_secure", False)
    monkeypatch.setattr(settings, "cors_allowed_origins", ORIGIN)


def tenant_world_iter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[World]:
    """A fully seeded world on a fresh SQLite database (the ``tenant_world`` fixture's body)."""
    configure_auth(monkeypatch)
    url = f"sqlite:///{tmp_path / 'tenant.db'}"
    migrate.upgrade(url)
    sessions = create_session_factory(create_db_engine(url, connect_args={"timeout": 30}))
    store = SqlEvidenceStore(sessions)
    reset_store()
    login_limiter.clear()
    app.dependency_overrides[get_store] = lambda: store
    try:
        with TestClient(app, base_url=ORIGIN) as root:
            yield build_world(root, sessions, backfill=True)
    finally:
        app.dependency_overrides.clear()
        reset_store()
        login_limiter.clear()
