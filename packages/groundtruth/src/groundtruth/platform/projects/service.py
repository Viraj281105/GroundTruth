"""Project operations. Functions flush but never commit: the caller owns the transaction."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from groundtruth.contracts.errors import GroundTruthError
from groundtruth.platform.audit.service import record_event
from groundtruth.platform.auth.authz import AccessContext, ProjectLevel
from groundtruth.platform.config import get_settings
from groundtruth.platform.projects.boundary import BoundaryResult, serialize_geojson
from groundtruth.platform.store.models import OrganizationRow, ProjectGrantRow, ProjectRow
from groundtruth.platform.tenancy.service import slugify

_SLUG_ATTEMPTS = 8


def _now() -> datetime:
    return datetime.now(UTC)


def project_slug_base(name: str) -> str:
    """Kebab slug for a project name. Never UUID-shaped (authz resolves by id OR slug)."""
    return slugify(name)


def _unique_project_slug(db: Session, base: str, tried: set[str]) -> str:
    taken = set(
        db.execute(select(ProjectRow.slug).where(ProjectRow.slug.like(f"{base}%"))).scalars().all()
    )
    slug, n = base, 2
    while slug in taken or slug in tried:
        slug = f"{base}-{n}"
        n += 1
    return slug


def boundary_file(project_id: str) -> Path:
    """Where an uploaded boundary lives. Built from a server-generated id, never user input."""
    return get_settings().cases_dir / "boundaries" / "projects" / f"{project_id}.geojson"


def _stored_path(path: Path) -> str:
    """Repo-relative POSIX path when possible (matches the YAML ``boundary_path`` style)."""
    try:
        return path.relative_to(get_settings().cases_dir.parent).as_posix()
    except ValueError:
        return path.as_posix()


def create_project(
    db: Session,
    ctx: AccessContext,
    *,
    name: str,
    country: str,
    ecosystem: str,
    intervention: str,
    treatment_start_year: int,
    boundary: BoundaryResult,
    request: Request | None = None,
) -> ProjectRow:
    """Create a project owned by ``ctx.org_id`` and write its boundary file.

    The file is written after the row is flushed; if writing fails the row is deleted again so
    no project exists without its boundary.
    """
    now = _now()
    project_id = str(uuid.uuid4())
    path = boundary_file(project_id)
    base = project_slug_base(name)
    tried: set[str] = set()
    row: ProjectRow | None = None
    for _ in range(_SLUG_ATTEMPTS):
        slug = _unique_project_slug(db, base, tried)
        candidate = ProjectRow(
            id=project_id,
            slug=slug,
            organization_id=ctx.org_id,
            case_id=None,
            name=name.strip(),
            country=country.strip(),
            ecosystem=ecosystem.strip(),
            intervention=intervention.strip(),
            treatment_start_year=treatment_start_year,
            boundary_path=_stored_path(path),
            boundary_sha256=boundary.sha256,
            data_mode="observed",
            created_by=ctx.user_id,
            created_at=now,
            updated_at=now,
        )
        try:
            with db.begin_nested():
                db.add(candidate)
                db.flush()
        except IntegrityError:
            tried.add(slug)
            continue
        row = candidate
        break
    if row is None:
        raise GroundTruthError("could not allocate a unique project slug")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(serialize_geojson(boundary.geojson))
    except OSError:
        db.delete(row)
        db.flush()
        path.unlink(missing_ok=True)
        raise
    record_event(
        db,
        action="project.create",
        outcome="success",
        actor_user_id=ctx.user_id,
        organization_id=ctx.org_id,
        resource_type="project",
        resource_id=row.id,
        request=request,
        details={"slug": row.slug, "area_ha": f"{boundary.area_ha:.2f}"},
    )
    return row


def get_project(db: Session, project_id_or_slug: str) -> ProjectRow | None:
    return db.execute(
        select(ProjectRow).where(
            (ProjectRow.id == project_id_or_slug) | (ProjectRow.slug == project_id_or_slug)
        )
    ).scalar_one_or_none()


def list_org_projects(db: Session, ctx: AccessContext) -> list[tuple[ProjectRow, ProjectLevel]]:
    """Projects the active org owns (OWNER) plus those granted to it (the grant's level)."""
    out: list[tuple[ProjectRow, ProjectLevel]] = [
        (p, ProjectLevel.OWNER)
        for p in db.execute(select(ProjectRow).where(ProjectRow.organization_id == ctx.org_id))
        .scalars()
        .all()
    ]
    granted = db.execute(
        select(ProjectRow, ProjectGrantRow.level)
        .join(ProjectGrantRow, ProjectGrantRow.project_id == ProjectRow.id)
        .where(
            ProjectGrantRow.grantee_organization_id == ctx.org_id,
            ProjectGrantRow.revoked_at.is_(None),
            ProjectRow.organization_id != ctx.org_id,
        )
    ).all()
    out += [(p, ProjectLevel(level)) for p, level in granted]
    out.sort(key=lambda pl: (pl[0].name.lower(), pl[0].id))
    return out


# --- grants -------------------------------------------------------------------------------------


def active_grants(db: Session, project_id: str) -> list[tuple[ProjectGrantRow, OrganizationRow]]:
    """Unrevoked grants of ``project_id`` with their grantee orgs, ordered by org slug."""
    rows = db.execute(
        select(ProjectGrantRow, OrganizationRow)
        .join(OrganizationRow, OrganizationRow.id == ProjectGrantRow.grantee_organization_id)
        .where(ProjectGrantRow.project_id == project_id, ProjectGrantRow.revoked_at.is_(None))
        .order_by(OrganizationRow.slug)
    ).all()
    return [(g, o) for g, o in rows]


def grant_project(
    db: Session,
    project: ProjectRow,
    grantee: OrganizationRow,
    level: str,
    *,
    actor_user_id: str,
) -> ProjectGrantRow:
    """Grant ``level`` on ``project`` to ``grantee``; reactivate a revoked grant (new level)
    rather than add a second row. Flushes, never commits."""
    now = _now()
    row = db.execute(
        select(ProjectGrantRow).where(
            ProjectGrantRow.project_id == project.id,
            ProjectGrantRow.grantee_organization_id == grantee.id,
        )
    ).scalar_one_or_none()
    if row is None:
        row = ProjectGrantRow(
            id=str(uuid.uuid4()),
            project_id=project.id,
            grantee_organization_id=grantee.id,
            level=level,
            granted_by=actor_user_id,
            created_at=now,
            revoked_at=None,
        )
        db.add(row)
    elif row.revoked_at is None and row.level == level:
        return row  # already active at this level: a true no-op
    else:
        row.level = level
        row.granted_by = actor_user_id
        row.created_at = now
        row.revoked_at = None
    db.flush()
    return row


def revoke_project_grant(
    db: Session, project: ProjectRow, grantee: OrganizationRow
) -> ProjectGrantRow | None:
    """Revoke the active grant (the row is kept for the audit trail); ``None`` if none."""
    row = db.execute(
        select(ProjectGrantRow).where(
            ProjectGrantRow.project_id == project.id,
            ProjectGrantRow.grantee_organization_id == grantee.id,
            ProjectGrantRow.revoked_at.is_(None),
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    row.revoked_at = _now()
    db.flush()
    return row
