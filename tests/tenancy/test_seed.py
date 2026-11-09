from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select

from groundtruth.platform.auth import passwords
from groundtruth.platform.projects.seed import seed
from groundtruth.platform.store.models import (
    AnalysisRunRow,
    CaseRow,
    JobRow,
    MembershipRow,
    OrganizationRow,
    ProjectGrantRow,
    ProjectRow,
    UserRow,
)

CASES = Path(__file__).resolve().parents[2] / "cases"


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    monkeypatch.setattr(passwords, "SCRYPT_N", 2**10)


def _counts(db) -> dict[str, int]:
    return {
        m.__tablename__: db.execute(select(func.count()).select_from(m)).scalar_one()
        for m in (OrganizationRow, ProjectRow, ProjectGrantRow, UserRow, MembershipRow, CaseRow)
    }


def test_seed_is_idempotent(tenancy_sessions):
    with tenancy_sessions() as db:
        first = seed(db, cases_dir=CASES, demo=True)
        db.commit()
        before = _counts(db)
    with tenancy_sessions() as db:
        second = seed(db, cases_dir=CASES, demo=True)
        db.commit()
        after = _counts(db)
    assert first.created > 0 and first.existing == 0
    assert second.created == 0 and second.existing == first.created
    assert before == after
    assert len(first.demo_users) == 4 and second.demo_users == []


def test_seed_kariba_owned_by_reference_and_granted(tenancy_sessions):
    with tenancy_sessions() as db:
        seed(db, cases_dir=CASES, demo=True)
        db.commit()
        ref = db.execute(
            select(OrganizationRow).where(OrganizationRow.slug == "reference")
        ).scalar_one()
        assert ref.type == "reference"
        kariba = db.execute(select(ProjectRow).where(ProjectRow.slug == "kariba-redd")).scalar_one()
        assert kariba.organization_id == ref.id and kariba.case_id == "kariba-redd"
        assert kariba.data_mode == "observed"
        assert kariba.boundary_path == "cases/boundaries/kariba-redd.geojson"
        assert (
            kariba.boundary_sha256
            == hashlib.sha256(
                (CASES / "boundaries" / "kariba-redd.geojson").read_bytes()
            ).hexdigest()
        )
        grants = dict(
            db.execute(
                select(OrganizationRow.slug, ProjectGrantRow.level)
                .join(
                    ProjectGrantRow, ProjectGrantRow.grantee_organization_id == OrganizationRow.id
                )
                .where(ProjectGrantRow.project_id == kariba.id)
            ).all()
        )
        assert grants == {
            "demo-ngo": "contribute",
            "demo-funder": "view",
            "demo-auditor": "audit",
            "demo-government": "view",
        }
        emails = set(db.execute(select(UserRow.email)).scalars())
        assert "ngo@demo.groundtruth.local" in emails
        assert all(u.role == "user" for u in db.execute(select(UserRow)).scalars())


def test_seed_without_demo_creates_no_users(tenancy_sessions):
    with tenancy_sessions() as db:
        report = seed(db, cases_dir=CASES, demo=False)
        db.commit()
        assert report.demo_users == []
        assert db.execute(select(func.count()).select_from(UserRow)).scalar_one() == 0
        assert db.execute(select(func.count()).select_from(ProjectGrantRow)).scalar_one() == 0


def test_benchmark_project_is_simulated(tenancy_sessions):
    with tenancy_sessions() as db:
        seed(db, cases_dir=CASES, demo=False)
        db.commit()
        row = db.execute(
            select(ProjectRow).where(ProjectRow.slug == "kariba-redd-benchmark")
        ).scalar_one()
        assert row.data_mode == "simulated"
        assert "SIMULATED" in row.name


def test_demo_passwords_are_strong_and_unique(tenancy_sessions):
    with tenancy_sessions() as db:
        report = seed(db, cases_dir=CASES, demo=True)
        pws = [p for _, p in report.demo_users]
        assert len(set(pws)) == 4 and all(len(p) >= 16 for p in pws)


def test_seed_backfills_project_ids(tenancy_sessions):
    now = datetime.now(UTC)
    with tenancy_sessions() as db:
        seed(db, cases_dir=CASES, demo=False)
        db.commit()
        db.add(
            AnalysisRunRow(
                run_id="r1",
                case_id="kariba-redd",
                spec_hash="h",
                data_mode="simulated",
                status="succeeded",
                is_simulated=True,
                seed=1,
                engine_version="t",
                engine_git_sha="t",
                engine_contract_version="x",
                contract_version="x",
                dataset_refs=[],
                created_at=now,
            )
        )
        db.flush()
        db.add(JobRow(run_id="r1"))
        db.commit()
    with tenancy_sessions() as db:
        seed(db, cases_dir=CASES, demo=False)
        db.commit()
        pid = db.execute(select(ProjectRow.id).where(ProjectRow.slug == "kariba-redd")).scalar_one()
        assert db.get(AnalysisRunRow, "r1").project_id == pid
        assert db.get(JobRow, "r1").project_id == pid


def test_seed_demo_then_real_first_user_is_admin(tenancy_sessions):
    from groundtruth.platform.auth.service import register

    with tenancy_sessions() as db:
        seed(db, cases_dir=CASES, demo=True)
        db.commit()
        real = register(db, "real@example.org", "correct horse battery")
        db.commit()
        assert real.role == "admin"
        later = register(db, "later@example.org", "correct horse battery")
        assert later.role == "user"
