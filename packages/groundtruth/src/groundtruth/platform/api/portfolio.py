"""Organization-scoped read routes: portfolio, audit log and activity feed.

The portfolio is built from the same engine assessment as ``/projects/{id}/assessment`` and only
reshaped. It never totals anything, keeps simulated projects in their own list, and shows funding
only as the amount the owning organization reported. The audit log is the full record for owners
and admins; the activity feed is the member-safe slice of it (no auth, membership or denial
events, and no actor, address or user agent).
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from groundtruth.platform.api.errors import ApiErrorBody
from groundtruth.platform.api.org_schemas import (
    ActivityItem,
    AuditEventView,
    AuditPage,
    DimensionStatuses,
    PortfolioRow,
    PortfolioView,
    ReportedFunding,
)
from groundtruth.platform.api.projects import project_views
from groundtruth.platform.audit.service import list_activity, list_events
from groundtruth.platform.auth.authz import (
    AccessContext,
    Action,
    ProjectLevel,
    require_org_action,
)
from groundtruth.platform.auth.deps import resolve_sessions
from groundtruth.platform.auth.service import auth_error
from groundtruth.platform.config import get_settings
from groundtruth.platform.projects import service, views
from groundtruth.platform.projects.assessment import build_project_assessment
from groundtruth.platform.projects.redaction import redact
from groundtruth.platform.store.models import ProjectRow

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/orgs", tags=["organizations"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ApiErrorBody, "description": "Not signed in."},
    403: {"model": ApiErrorBody, "description": "Your role does not allow this."},
    404: {"model": ApiErrorBody, "description": "Unknown organization."},
    422: {"model": ApiErrorBody, "description": "Invalid cursor or limit."},
    503: {"model": ApiErrorBody, "description": "No database is configured."},
}

Viewer = Annotated[AccessContext, Depends(require_org_action(Action.VIEW_ORG))]
AuditViewer = Annotated[AccessContext, Depends(require_org_action(Action.VIEW_AUDIT))]

_DIMENSIONS = {
    "trajectory": "vegetation_trajectory",
    "risk": "ecological_risk",
    "evidence_quality": "evidence_quality",
}


def portfolio_row(
    db: Session, project: ProjectRow, level: ProjectLevel, ctx: AccessContext
) -> dict[str, Any]:
    """One redacted portfolio row for ``project`` as seen at ``level`` by ``ctx``'s org.

    One project's failure must not 500 the whole portfolio: any error while assessing it is
    logged and the row degrades to level 0 with ``degraded`` set. No value is invented.
    """
    project_view = project_views(db, [(project, level)])[0]
    funding = None
    if project.reported_funding_amount is not None:
        funding = ReportedFunding(
            amount=float(project.reported_funding_amount),
            currency=project.reported_funding_currency,
            reported_by=project_view.owner_name,
        )
    try:
        view = views.build_assessment(
            build_project_assessment(project, data_dir=get_settings().data_dir),
            project,
            level.value,
        )
        by_id = {d.id: d.status for d in view.dimensions}
        statuses = DimensionStatuses(
            **{k: by_id.get(d, "Insufficient evidence") for k, d in _DIMENSIONS.items()}
        )
        # ``recommendations`` are ordered by priority; first one for this persona wins.
        top = next((r for r in view.recommendations if ctx.org_type in r.personas), None)
        row = PortfolioRow(
            project=project_view,
            access_level=level.value,  # type: ignore[arg-type]
            assessment_level=view.level,
            level_name=view.level_name,
            dimension_statuses=statuses,
            top_recommendation=top,
            attribution_verdict=view.attribution.verdict,
            evidence_confidence=view.evidence_confidence,
            data_mode=view.data_mode,
            reported_funding=funding,
        )
        return jsonable_encoder(redact(row, level))
    except Exception:
        logger.exception("portfolio row for project %s degraded", project.id)
        unknown = "Insufficient evidence"
        degraded = PortfolioRow(
            project=project_view,
            access_level=level.value,  # type: ignore[arg-type]
            assessment_level=0,
            level_name="Not assessable",
            dimension_statuses=DimensionStatuses(
                trajectory=unknown, risk=unknown, evidence_quality=unknown
            ),
            top_recommendation=None,
            attribution_verdict=None,
            evidence_confidence=None,
            data_mode=views.data_mode_of(project),  # type: ignore[arg-type]
            reported_funding=funding,
            degraded=True,
            degraded_reason="assessment unavailable",
        )
        return jsonable_encoder(redact(degraded, level))


@router.get(
    "/{slug}/portfolio",
    summary="Assessment level, dimension statuses and top recommendation per project",
    responses={200: {"model": PortfolioView}, **{k: v for k, v in _ERRORS.items() if k != 422}},
)
def get_portfolio(request: Request, ctx: Viewer) -> JSONResponse:
    """Every project the organization owns or was granted. Simulated projects are listed apart
    and nothing is aggregated across projects. Fields the project's access level may not see are
    removed, never altered."""
    real: list[tuple[int, str, str, dict[str, Any]]] = []
    simulated: list[tuple[int, str, str, dict[str, Any]]] = []
    with resolve_sessions(request)() as db:
        for project, level in service.list_org_projects(db, ctx):
            row = portfolio_row(db, project, level, ctx)
            entry = (-row["assessment_level"], project.name, project.id, row)
            (simulated if row["data_mode"] == "simulated" else real).append(entry)
    return JSONResponse(
        {
            "projects": [e[3] for e in sorted(real, key=lambda e: e[:3])],
            "simulated": [e[3] for e in sorted(simulated, key=lambda e: e[:3])],
        }
    )


@router.get(
    "/{slug}/audit",
    response_model=AuditPage,
    summary="The organization's audit log, newest first (owners and admins)",
    responses=_ERRORS,
)
def get_audit(
    request: Request,
    ctx: AuditViewer,
    cursor: Annotated[str | None, Query(description="`next_cursor` of the previous page.")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> AuditPage:
    """Security-relevant events of your active organization (`slug` must be it), newest first. Page
    with `cursor` and `limit` (1 to 200). Needs a role that may read the audit log (403 otherwise).
    A cursor that is not valid is 422 `invalid_cursor`; note that `GET /runs` answers the same code
    with 400."""
    with resolve_sessions(request)() as db:
        try:
            rows, next_cursor = list_events(db, ctx.org_id, cursor=cursor, limit=limit)
        except ValueError as exc:
            raise auth_error("invalid_cursor", "The cursor is not valid.") from exc
        return AuditPage(
            events=[
                AuditEventView(
                    id=r.id,
                    occurred_at=r.occurred_at,
                    actor_user_id=r.actor_user_id,
                    action=r.action,
                    resource_type=r.resource_type,
                    resource_id=r.resource_id,
                    outcome=r.outcome,
                    ip=r.ip,
                    user_agent=r.user_agent,
                    details=dict(r.details or {}),
                )
                for r in rows
            ],
            next_cursor=next_cursor,
        )


@router.get(
    "/{slug}/activity",
    response_model=list[ActivityItem],
    summary="Recent project, run and export activity (every member)",
    responses=_ERRORS,
)
def get_activity(
    request: Request,
    ctx: Viewer,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[ActivityItem]:
    """Only `project.*`, `run.*` and `export.*` events on projects the organization can access:
    its own actions, and anyone's on a project it owns. No authentication, membership or
    authorization events, and no actor, IP address, user agent or details."""
    with resolve_sessions(request)() as db:
        accessible = service.list_org_projects(db, ctx)
        by_id = {p.id: p for p, _ in accessible}
        owned = frozenset(p.id for p, lvl in accessible if lvl is ProjectLevel.OWNER)
        rows = list_activity(
            db,
            ctx.org_id,
            accessible_project_ids=frozenset(by_id),
            owned_project_ids=owned,
            limit=limit,
        )
        items: list[ActivityItem] = []
        for r in rows:
            pid = (
                r.resource_id
                if r.resource_type == "project"
                else (r.details or {}).get("project_id")
            )
            project = by_id.get(pid) if isinstance(pid, str) else None
            items.append(
                ActivityItem(
                    id=r.id,
                    occurred_at=r.occurred_at,
                    action=r.action,
                    outcome=r.outcome,
                    project_id=project.id if project else None,
                    project_slug=project.slug if project else None,
                    project_name=project.name if project else None,
                    own=r.organization_id == ctx.org_id,
                )
            )
        return items
