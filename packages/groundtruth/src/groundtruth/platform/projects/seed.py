"""Idempotent seed: the Reference org, every YAML case as a project, optional demo tenants.

Safe to re-run. Existing rows are left untouched (in particular an existing demo user keeps
its password) and are counted as ``existing``. The caller commits.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from groundtruth.platform.auth.service import DEFAULT_ROLE, register
from groundtruth.platform.cases.registry import CaseDefinition, load_all_cases
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
from groundtruth.platform.store.sql import _case_definition

REFERENCE_SLUG = "reference"
KARIBA_ID = "kariba-redd"
BENCHMARK_SLUG = "kariba-redd-benchmark"
DEMO_DOMAIN = "demo.groundtruth.local"

# (org slug, org name, org type, user local-part, grant level on Kariba)
DEMO_TENANTS: tuple[tuple[str, str, str, str, str], ...] = (
    ("demo-ngo", "Demo NGO", "ngo", "ngo", "contribute"),
    ("demo-funder", "Demo Funder", "funder", "funder", "view"),
    ("demo-auditor", "Demo Auditor", "auditor", "auditor", "audit"),
    ("demo-government", "Demo Government", "government", "government", "view"),
)


@dataclass
class SeedReport:
    created: int = 0
    existing: int = 0
    demo_users: list[tuple[str, str]] = field(default_factory=list)
    """``(email, password)`` for demo users created by this run only. Shown once."""
    existing_demo_users: list[str] = field(default_factory=list)
    """Demo users that already existed; their passwords were not touched."""
    backfilled_runs: int = 0
    backfilled_jobs: int = 0

    def _count(self, created: bool) -> None:
        if created:
            self.created += 1
        else:
            self.existing += 1


def _now() -> datetime:
    return datetime.now(UTC)


def _ensure_org(db: Session, report: SeedReport, *, slug: str, name: str, type_: str) -> str:
    org = db.execute(
        select(OrganizationRow).where(OrganizationRow.slug == slug)
    ).scalar_one_or_none()
    report._count(org is None)
    if org is None:
        org = OrganizationRow(
            id=str(uuid.uuid4()), slug=slug, name=name, type=type_, created_at=_now()
        )
        db.add(org)
        db.flush()
    return org.id


def _upsert_case_row(db: Session, case: CaseDefinition) -> None:
    """Mirror the YAML case into ``cases`` (same shape as ``SqlEvidenceStore.upsert_case``)."""
    row = db.get(CaseRow, case.case_id)
    if row is None:
        row = CaseRow(case_id=case.case_id)
        db.add(row)
    row.name = case.claim.name
    row.country = case.claim.country
    row.indicator = case.indicator.value
    row.status = case.status
    row.definition = _case_definition(case)
    db.flush()


def _boundary(cases_dir: Path, case: CaseDefinition) -> tuple[str, str] | None:
    declared = case.claim.boundary_path
    if not declared:
        return None
    file = cases_dir / "boundaries" / Path(declared).name
    if not file.is_file():
        return None
    return declared, hashlib.sha256(file.read_bytes()).hexdigest()


def _ensure_project(
    db: Session,
    report: SeedReport,
    *,
    org_id: str,
    slug: str,
    case: CaseDefinition,
    case_id: str | None,
    name: str,
    data_mode: str,
    boundary: tuple[str, str] | None,
) -> ProjectRow:
    row = db.execute(select(ProjectRow).where(ProjectRow.slug == slug)).scalar_one_or_none()
    report._count(row is None)
    if row is not None:
        return row
    now = _now()
    start = case.claim.crediting_period_start
    row = ProjectRow(
        id=str(uuid.uuid4()),
        slug=slug,
        organization_id=org_id,
        case_id=case_id,
        name=name,
        country=case.claim.country,
        ecosystem=case.ecosystem,
        intervention=case.claim.standard.value,
        treatment_start_year=start.year if start is not None else case.window.post_start,
        boundary_path=boundary[0] if boundary else None,
        boundary_sha256=boundary[1] if boundary else None,
        data_mode=data_mode,
        created_by=None,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    return row


def _ensure_demo(db: Session, report: SeedReport, kariba: ProjectRow) -> None:
    for slug, name, type_, local, level in DEMO_TENANTS:
        email = f"{local}@{DEMO_DOMAIN}"
        org_id = _ensure_org(db, report, slug=slug, name=name, type_=type_)
        user = db.execute(select(UserRow).where(UserRow.email == email)).scalar_one_or_none()
        report._count(user is None)
        if user is None:
            password = secrets.token_urlsafe(18)
            user = register(db, email, password)
            # A demo account must never be a global admin (register() only grants admin
            # while none exists, so keep that bootstrap for a real first user).
            user.role = DEFAULT_ROLE
            report.demo_users.append((email, password))
        else:
            report.existing_demo_users.append(email)
        if (
            db.execute(
                select(MembershipRow.id).where(
                    MembershipRow.user_id == user.id, MembershipRow.organization_id == org_id
                )
            ).first()
            is None
        ):
            db.add(
                MembershipRow(
                    id=str(uuid.uuid4()),
                    user_id=user.id,
                    organization_id=org_id,
                    role="owner",
                    created_at=_now(),
                )
            )
        grant = db.execute(
            select(ProjectGrantRow).where(
                ProjectGrantRow.project_id == kariba.id,
                ProjectGrantRow.grantee_organization_id == org_id,
            )
        ).scalar_one_or_none()
        report._count(grant is None)
        if grant is None:
            db.add(
                ProjectGrantRow(
                    id=str(uuid.uuid4()),
                    project_id=kariba.id,
                    grantee_organization_id=org_id,
                    level=level,
                    granted_by=None,
                    created_at=_now(),
                )
            )
        db.flush()
    # In demo mode, ensure existing unattached users have access to demo-ngo so they
    # can enter the workspace after sign-in.
    ngo_org_id = db.execute(
        select(OrganizationRow.id).where(OrganizationRow.slug == "demo-ngo")
    ).scalar_one_or_none()
    if ngo_org_id is not None:
        unattached = (
            db.execute(
                select(UserRow).where(
                    ~select(MembershipRow.id).where(MembershipRow.user_id == UserRow.id).exists()
                )
            )
            .scalars()
            .all()
        )
        for u in unattached:
            db.add(
                MembershipRow(
                    id=str(uuid.uuid4()),
                    user_id=u.id,
                    organization_id=ngo_org_id,
                    role="owner",
                    created_at=_now(),
                )
            )
        db.flush()


def _backfill_project_ids(db: Session, report: SeedReport) -> None:
    """Point legacy runs and jobs at their project (the migration backfill was a no-op)."""
    project_for_case = (
        select(ProjectRow.id).where(ProjectRow.case_id == AnalysisRunRow.case_id).scalar_subquery()
    )
    result = db.execute(
        update(AnalysisRunRow)
        .where(AnalysisRunRow.project_id.is_(None))
        .values(project_id=project_for_case)
    )
    report.backfilled_runs = max(getattr(result, "rowcount", 0) or 0, 0)
    run_project = (
        select(AnalysisRunRow.project_id)
        .where(AnalysisRunRow.run_id == JobRow.run_id)
        .scalar_subquery()
    )
    result = db.execute(
        update(JobRow).where(JobRow.project_id.is_(None)).values(project_id=run_project)
    )
    report.backfilled_jobs = max(getattr(result, "rowcount", 0) or 0, 0)


def seed(db: Session, *, cases_dir: Path, demo: bool) -> SeedReport:
    """Create the Reference org and projects (and demo tenants when ``demo``). Idempotent."""
    report = SeedReport()
    reference_id = _ensure_org(
        db, report, slug=REFERENCE_SLUG, name="GroundTruth Reference", type_="reference"
    )
    cases = load_all_cases(cases_dir)
    for case_id, case in cases.items():
        _upsert_case_row(db, case)
        _ensure_project(
            db,
            report,
            org_id=reference_id,
            slug=case_id,
            case=case,
            case_id=case_id,
            name=case.claim.name,
            # Only Kariba has a verified boundary and registry-derived inputs; every other
            # case is a scaffold with no observed data, so it must not claim to be observed.
            data_mode="observed" if case_id == KARIBA_ID else "simulated",
            boundary=_boundary(cases_dir, case) if case_id == KARIBA_ID else None,
        )
    kariba_case = cases.get(KARIBA_ID)
    kariba = db.execute(select(ProjectRow).where(ProjectRow.slug == KARIBA_ID)).scalar_one_or_none()
    if kariba_case is not None and kariba is not None:
        # case_id is unique, so the benchmark has none; it shares Kariba's boundary on purpose.
        _ensure_project(
            db,
            report,
            org_id=reference_id,
            slug=BENCHMARK_SLUG,
            case=kariba_case,
            case_id=None,
            name="Kariba REDD+ (SIMULATED benchmark)",
            data_mode="simulated",
            boundary=_boundary(cases_dir, kariba_case),
        )
        if demo:
            _ensure_demo(db, report, kariba)
    _backfill_project_ids(db, report)
    db.flush()
    return report
