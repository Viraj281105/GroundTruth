"""Project scoping for the routes that name a case, run or job instead of a project.

The project is the unit of authorization (design spec section 4). A case belongs to the
project whose ``case_id`` names it; a run or job belongs to the project in its
``project_id``. Everything here funnels into ``authorize_project`` so a case route, a run
route and ``/projects/{id}`` cannot drift apart.

A run or job with no ``project_id`` (a legacy row the seed has not backfilled) belongs to no
project and is therefore readable by nobody: failing closed is the only safe reading of "no
owner".
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from groundtruth.platform.api.errors import ApiErrorCode, api_error
from groundtruth.platform.audit.service import record_event
from groundtruth.platform.auth.authz import (
    AccessContext,
    Action,
    Capability,
    Context,
    NotFound,
    ProjectAccess,
    authorize_project,
)
from groundtruth.platform.auth.deps import resolve_sessions
from groundtruth.platform.projects.service import list_org_projects
from groundtruth.platform.store.models import ProjectRow


def case_not_found(case_id: str, *, structured: bool = False) -> NotFound:
    """The 404 for a case that is unknown or not visible (one body for both).

    ``structured`` picks the family's body: ``{code, message, hint}`` for the job and map
    routes, or the plain-message ``detail`` string ``/cases/{id}`` and ``/verify`` document.
    """
    if structured:
        return lambda: api_error(ApiErrorCode.CASE_NOT_FOUND, f"No case {case_id!r}.")
    return lambda: HTTPException(status_code=404, detail=f"Unknown case {case_id!r}.")


def run_not_found(run_id: str, noun: str = "run") -> NotFound:
    return lambda: api_error(ApiErrorCode.RUN_NOT_FOUND, f"No {noun} {run_id!r}.")


def authorize_case(
    request: Request,
    ctx: AccessContext,
    case_id: str,
    cap: Capability,
    *,
    action: Action | None = None,
    structured: bool = False,
) -> ProjectAccess:
    """The caller's access to the project that owns ``case_id`` (404 if none, or no access)."""

    def lookup(db: Session) -> ProjectRow | None:
        return db.execute(
            select(ProjectRow).where(ProjectRow.case_id == case_id)
        ).scalar_one_or_none()

    return authorize_project(
        request,
        ctx,
        lookup,
        cap,
        action=action,
        not_found=case_not_found(case_id, structured=structured),
    )


def authorize_filed(
    request: Request,
    ctx: AccessContext,
    project_id: str | None,
    cap: Capability,
    *,
    not_found: NotFound,
    action: Action | None = None,
) -> ProjectAccess:
    """The caller's access to the project a run or job is filed under.

    ``project_id`` is ``None`` for an unfiled run, which is not found for everyone.
    """

    def lookup(db: Session) -> ProjectRow | None:
        return db.get(ProjectRow, project_id) if project_id is not None else None

    return authorize_project(request, ctx, lookup, cap, action=action, not_found=not_found)


def case_dependency(
    cap: Capability, *, action: Action | None = None, structured: bool = False
) -> Callable[..., ProjectAccess]:
    """Dependency for a route with a ``{case_id}`` path parameter."""

    def dependency(case_id: str, request: Request, ctx: Context) -> ProjectAccess:
        return authorize_case(request, ctx, case_id, cap, action=action, structured=structured)

    dependency.__gt_authz__ = "project"  # type: ignore[attr-defined]
    return dependency


def accessible_projects(request: Request, ctx: AccessContext) -> list[ProjectRow]:
    """Every project the active org owns or has been granted (all levels grant OVERVIEW)."""
    with resolve_sessions(request)() as db:
        projects = [p for p, _level in list_org_projects(db, ctx)]
        for p in projects:
            db.expunge(p)
        return projects


def audit(
    request: Request,
    ctx: AccessContext,
    *,
    action: str,
    resource_type: str,
    resource_id: str | None,
    details: Mapping[str, Any] | None = None,
) -> None:
    """Record a success event in its own transaction (the route has already done the work)."""
    with resolve_sessions(request)() as db:
        record_event(
            db,
            action=action,
            outcome="success",
            actor_user_id=ctx.user_id,
            organization_id=ctx.org_id,
            resource_type=resource_type,
            resource_id=resource_id,
            request=request,
            details=details,
        )
        db.commit()
