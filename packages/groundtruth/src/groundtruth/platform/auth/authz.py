"""Authorization core: organization roles, project access levels, FastAPI dependencies.

Two tables decide everything (design spec section 4) and are kept as module-level literals
so tests can compare them with an independent copy. A caller with no access to a project
gets the same 404 as for a project that does not exist; only a caller who can see the
project gets a 403. These dependencies always require a session: ``AUTH_REQUIRED=false``
does not bypass them, because tenancy is meaningless for an anonymous caller.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from groundtruth.platform.audit.service import record_event
from groundtruth.platform.auth.deps import resolve_sessions, session_token
from groundtruth.platform.auth.service import auth_error
from groundtruth.platform.auth.sessions import hash_token, resolve_session
from groundtruth.platform.store.models import (
    MembershipRow,
    OrganizationRow,
    ProjectGrantRow,
    ProjectRow,
    SessionRow,
)


class Action(StrEnum):
    VIEW_ORG = "view_org"
    CREATE_PROJECT = "create_project"
    EDIT_PROJECT = "edit_project"
    START_RUN = "start_run"
    MANAGE_MEMBERS = "manage_members"
    MANAGE_GRANTS = "manage_grants"
    VIEW_AUDIT = "view_audit"
    DELETE_ORG = "delete_org"


class Capability(StrEnum):
    OVERVIEW = "overview"
    SERIES = "series"
    EVIDENCE_FULL = "evidence_full"
    DIAGNOSTICS = "diagnostics"
    DOSSIER_EXPORT = "dossier_export"
    REPORT_EXPORT = "report_export"
    EDIT = "edit"
    FIELD_CONTRIBUTE = "field_contribute"


class ProjectLevel(StrEnum):
    OWNER = "owner"
    AUDIT = "audit"
    CONTRIBUTE = "contribute"
    VIEW = "view"


@dataclass(frozen=True)
class AccessContext:
    user_id: str
    org_id: str
    org_type: str
    role: str


ORG_ACTION_TABLE: dict[Action, frozenset[str]] = {
    Action.VIEW_ORG: frozenset({"owner", "admin", "member", "viewer"}),
    Action.CREATE_PROJECT: frozenset({"owner", "admin", "member"}),
    Action.EDIT_PROJECT: frozenset({"owner", "admin", "member"}),
    Action.START_RUN: frozenset({"owner", "admin", "member"}),
    Action.MANAGE_MEMBERS: frozenset({"owner", "admin"}),
    Action.MANAGE_GRANTS: frozenset({"owner", "admin"}),
    Action.VIEW_AUDIT: frozenset({"owner", "admin"}),
    Action.DELETE_ORG: frozenset({"owner"}),
}
"""Action -> membership roles allowed to perform it."""

_O = ProjectLevel.OWNER
_A = ProjectLevel.AUDIT
_C = ProjectLevel.CONTRIBUTE
_V = ProjectLevel.VIEW

PROJECT_CAPABILITY_TABLE: dict[Capability, frozenset[ProjectLevel]] = {
    Capability.OVERVIEW: frozenset({_O, _A, _C, _V}),
    Capability.SERIES: frozenset({_O, _A, _C, _V}),
    Capability.EVIDENCE_FULL: frozenset({_O, _A, _C}),  # a view grant gets the summary only
    Capability.DIAGNOSTICS: frozenset({_O, _A}),
    Capability.DOSSIER_EXPORT: frozenset({_O, _A}),
    Capability.REPORT_EXPORT: frozenset({_O, _A, _C, _V}),
    Capability.EDIT: frozenset({_O}),  # additionally role-gated by Action.EDIT_PROJECT
    Capability.FIELD_CONTRIBUTE: frozenset({_O, _C}),
}
"""Capability -> project levels that have it."""


def org_allows(role: str, action: Action) -> bool:
    return role in ORG_ACTION_TABLE[action]


def level_allows(level: ProjectLevel, cap: Capability) -> bool:
    return level in PROJECT_CAPABILITY_TABLE[cap]


def can_use(ctx: AccessContext, level: ProjectLevel, cap: Capability) -> bool:
    """``level_allows`` plus the membership-role gate that ``EDIT`` also needs."""
    if not level_allows(level, cap):
        return False
    return cap is not Capability.EDIT or org_allows(ctx.role, Action.EDIT_PROJECT)


def project_level(db: Session, ctx: AccessContext, project: ProjectRow) -> ProjectLevel | None:
    """OWNER for the owning org, else the active (unrevoked) grant to ``ctx.org_id``."""
    if ctx.org_id == project.organization_id:
        return ProjectLevel.OWNER
    level = db.execute(
        select(ProjectGrantRow.level).where(
            ProjectGrantRow.project_id == project.id,
            ProjectGrantRow.grantee_organization_id == ctx.org_id,
            ProjectGrantRow.revoked_at.is_(None),
        )
    ).scalar_one_or_none()
    return ProjectLevel(level) if level is not None else None


@dataclass(frozen=True)
class ProjectAccess:
    ctx: AccessContext
    project: ProjectRow
    level: ProjectLevel


def _unauthenticated() -> HTTPException:
    return auth_error("unauthenticated", "Sign in to continue.")


def _no_active_org() -> HTTPException:
    return auth_error("no_active_organization", "Choose an organization to act for.")


def get_access_context(request: Request) -> AccessContext:
    """The caller's user, active organization and role, re-checked on every request.

    Raises:
        HTTPException: 401 without a live session; 409 ``no_active_organization`` when no
            organization can be chosen or the active one is no longer one the user belongs to.
    """
    token = session_token(request)
    if not token:
        raise _unauthenticated()
    sessions = resolve_sessions(request)
    with sessions() as db:
        user = resolve_session(db, token)
        if user is None:
            raise _unauthenticated()
        row = db.execute(
            select(SessionRow).where(SessionRow.token_hash == hash_token(token))
        ).scalar_one()
        memberships = {
            m.organization_id: m
            for m in db.execute(select(MembershipRow).where(MembershipRow.user_id == user.id))
            .scalars()
            .all()
        }
        active = row.active_organization_id
        if active is not None and active not in memberships:
            row.active_organization_id = None
            db.commit()
            raise _no_active_org()
        if active is None:
            if len(memberships) != 1:
                raise _no_active_org()
            active = next(iter(memberships))
            row.active_organization_id = active
            db.commit()
        org = db.get(OrganizationRow, active)
        if org is None:  # cannot happen with the FK, but never allow on a missing row
            raise _no_active_org()
        return AccessContext(
            user_id=user.id, org_id=org.id, org_type=org.type, role=memberships[active].role
        )


get_access_context.__gt_authz__ = "context"  # type: ignore[attr-defined]
"""Marker the route safety-net test matches on (a qualname can be spoofed)."""

Context = Annotated[AccessContext, Depends(get_access_context)]


def _deny(
    request: Request,
    ctx: AccessContext,
    *,
    resource_id: str | None,
    resource_type: str,
    details: dict[str, str],
) -> None:
    """Audit an authorization denial (throttled inside ``record_event``)."""
    with resolve_sessions(request)() as db:
        record_event(
            db,
            action="authz.denied",
            outcome="denied",
            actor_user_id=ctx.user_id,
            organization_id=ctx.org_id,
            resource_type=resource_type,
            resource_id=resource_id,
            request=request,
            details=details,
        )
        db.commit()


def require_org_action(action: Action) -> Callable[..., AccessContext]:
    """Dependency: path ``slug`` must be the active org's, and the role must allow ``action``."""

    def dependency(slug: str, request: Request, ctx: Context) -> AccessContext:
        with resolve_sessions(request)() as db:
            active_slug = db.execute(
                select(OrganizationRow.slug).where(OrganizationRow.id == ctx.org_id)
            ).scalar_one_or_none()
        if slug != active_slug:
            raise auth_error("not_found", "Organization not found.")
        if not org_allows(ctx.role, action):
            _deny(
                request,
                ctx,
                resource_type="organization",
                resource_id=ctx.org_id,
                details={"action": action.value, "reason": "role"},
            )
            raise auth_error("forbidden", "Your role is not allowed to do this.")
        return ctx

    dependency.__gt_authz__ = "org"  # type: ignore[attr-defined]
    return dependency


ProjectLookup = Callable[[Session], ProjectRow | None]
NotFound = Callable[[], HTTPException]


def _project_not_found() -> HTTPException:
    return auth_error("not_found", "Project not found.")


def authorize_project(
    request: Request,
    ctx: AccessContext,
    lookup: ProjectLookup,
    cap: Capability,
    *,
    action: Action | None = None,
    not_found: NotFound = _project_not_found,
) -> ProjectAccess:
    """Resolve a project through ``lookup`` and require capability ``cap`` on it.

    The one authorization path behind every project-scoped route, whatever the route names
    the project by (id or slug, case id, run, job). A missing project and a project the caller
    cannot see raise the same ``not_found()`` so existence is never revealed; only a caller
    who can see the project gets 403 (level too low, or ``action`` not allowed by their role).
    Each route family passes its own ``not_found`` so its 404 body matches its unknown-id 404.
    """
    with resolve_sessions(request)() as db:
        project = lookup(db)
        level = project_level(db, ctx, project) if project is not None else None
        if project is None or level is None:
            _deny(
                request,
                ctx,
                resource_type="project",
                resource_id=project.id if project is not None else None,
                details={"capability": cap.value, "reason": "no_access"},
            )
            raise not_found()
        if not can_use(ctx, level, cap):
            _deny(
                request,
                ctx,
                resource_type="project",
                resource_id=project.id,
                details={"capability": cap.value, "level": level.value, "reason": "level"},
            )
            raise auth_error("forbidden", "Your access level does not allow this.")
        if action is not None and not org_allows(ctx.role, action):
            _deny(
                request,
                ctx,
                resource_type="project",
                resource_id=project.id,
                details={"action": action.value, "level": level.value, "reason": "role"},
            )
            raise auth_error("forbidden", "Your role is not allowed to do this.")
        db.expunge(project)
        return ProjectAccess(ctx=ctx, project=project, level=level)


def require_project(
    cap: Capability, *, action: Action | None = None
) -> Callable[..., ProjectAccess]:
    """Dependency: resolve path ``project_id`` (id or slug) and require capability ``cap``.

    ``action`` additionally requires the caller's membership role to allow it (grant
    management is ``EDIT`` (owner level) plus ``Action.MANAGE_GRANTS``).

    Unknown project and no access share one 404 so existence is never revealed.
    """

    def dependency(project_id: str, request: Request, ctx: Context) -> ProjectAccess:
        def lookup(db: Session) -> ProjectRow | None:
            return db.execute(
                select(ProjectRow).where(
                    (ProjectRow.id == project_id) | (ProjectRow.slug == project_id)
                )
            ).scalar_one_or_none()

        return authorize_project(request, ctx, lookup, cap, action=action)

    dependency.__gt_authz__ = "project"  # type: ignore[attr-defined]
    return dependency
