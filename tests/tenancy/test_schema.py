from __future__ import annotations

from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from groundtruth.platform.store import migrate
from groundtruth.platform.store.database import create_db_engine
from groundtruth.platform.store.models import (
    GRANT_LEVELS,
    MEMBER_ROLES,
    ORG_TYPES,
    CaseRow,
    MembershipRow,
    OrganizationRow,
    ProjectGrantRow,
    ProjectRow,
    UserRow,
)

NOW = datetime(2026, 11, 8, tzinfo=UTC)


def test_constants() -> None:
    assert ORG_TYPES == ("ngo", "funder", "auditor", "government", "reference")
    assert MEMBER_ROLES == ("owner", "admin", "member", "viewer")
    assert GRANT_LEVELS == ("view", "audit", "contribute")


def _org(id_: str, type_: str = "ngo") -> OrganizationRow:
    return OrganizationRow(id=id_, slug=f"org-{id_}", name=f"Org {id_}", type=type_, created_at=NOW)


def _user(id_: str) -> UserRow:
    return UserRow(
        id=id_,
        email=f"{id_}@example.test",
        password_hash="x",
        role="user",
        is_active=True,
        created_at=NOW,
    )


def _project(id_: str, org_id: str) -> ProjectRow:
    return ProjectRow(
        id=id_,
        slug=f"proj-{id_}",
        organization_id=org_id,
        name="P",
        country="Kenya",
        ecosystem="mangrove",
        intervention="restoration",
        treatment_start_year=2015,
        data_mode="observed",
        created_at=NOW,
        updated_at=NOW,
    )


def test_upgrade_creates_tenancy_tables(tenancy_db_url: str) -> None:
    migrate.upgrade(tenancy_db_url)
    tables = set(sa.inspect(create_db_engine(tenancy_db_url)).get_table_names())
    assert {"organizations", "memberships", "projects", "project_grants", "audit_events"} <= tables


def test_org_type_check_constraint(tenancy_sessions: sessionmaker[Session]) -> None:
    with tenancy_sessions() as s, pytest.raises(IntegrityError):
        s.add(_org("o1", "bank"))
        s.commit()


def test_membership_unique_per_user_org(tenancy_sessions: sessionmaker[Session]) -> None:
    with tenancy_sessions() as s:
        s.add_all([_org("o1"), _user("u1")])
        s.commit()
        s.add(
            MembershipRow(id="m1", user_id="u1", organization_id="o1", role="owner", created_at=NOW)
        )
        s.commit()
        s.add(
            MembershipRow(
                id="m2", user_id="u1", organization_id="o1", role="member", created_at=NOW
            )
        )
        with pytest.raises(IntegrityError):
            s.commit()


def test_membership_role_check_constraint(tenancy_sessions: sessionmaker[Session]) -> None:
    with tenancy_sessions() as s:
        s.add_all([_org("o1"), _user("u1")])
        s.commit()
        s.add(
            MembershipRow(id="m1", user_id="u1", organization_id="o1", role="god", created_at=NOW)
        )
        with pytest.raises(IntegrityError):
            s.commit()


def test_grant_unique_per_project_org(tenancy_sessions: sessionmaker[Session]) -> None:
    with tenancy_sessions() as s:
        s.add_all([_org("o1", "reference"), _org("o2", "funder"), _user("u1")])
        s.commit()
        s.add(_project("p1", "o1"))
        s.commit()
        s.add(
            ProjectGrantRow(
                id="g1",
                project_id="p1",
                grantee_organization_id="o2",
                level="view",
                granted_by="u1",
                created_at=NOW,
            )
        )
        s.commit()
        s.add(
            ProjectGrantRow(
                id="g2",
                project_id="p1",
                grantee_organization_id="o2",
                level="audit",
                granted_by="u1",
                created_at=NOW,
            )
        )
        with pytest.raises(IntegrityError):
            s.commit()


def test_project_created_by_nullable_and_case_id_unique(
    tenancy_sessions: sessionmaker[Session],
) -> None:
    with tenancy_sessions() as s:
        s.add_all(
            [
                _org("o1", "reference"),
                CaseRow(
                    case_id="kariba-redd",
                    name="Kariba",
                    country="Zimbabwe",
                    indicator="ndvi",
                    status="scaffolded",
                    definition={},
                ),
            ]
        )
        s.commit()
        a, b = _project("p1", "o1"), _project("p2", "o1")
        a.case_id = b.case_id = "kariba-redd"
        s.add(a)
        s.commit()
        s.add(b)
        with pytest.raises(IntegrityError):
            s.commit()


def test_downgrade_roundtrip(tenancy_db_url: str) -> None:
    migrate.upgrade(tenancy_db_url)
    migrate.downgrade(tenancy_db_url, "0006")
    inspector = sa.inspect(create_db_engine(tenancy_db_url))
    assert "organizations" not in inspector.get_table_names()
    assert "active_organization_id" not in {c["name"] for c in inspector.get_columns("sessions")}
    assert "project_id" not in {c["name"] for c in inspector.get_columns("jobs")}
    migrate.upgrade(tenancy_db_url)
    inspector = sa.inspect(create_db_engine(tenancy_db_url))
    assert "active_organization_id" in {c["name"] for c in inspector.get_columns("sessions")}
    assert "project_id" in {c["name"] for c in inspector.get_columns("analysis_runs")}
