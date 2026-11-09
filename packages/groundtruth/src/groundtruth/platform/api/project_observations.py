"""Observation-ingestion routes: request satellite observations for a project, and watch them.

A request is validated against the project's own boundary and queued; the worker process runs it
(see ``platform/projects/ingestion.py``). These routes never fetch anything themselves, so a slow
or unreachable satellite provider cannot hang the API, and a request can only ever target a
project the caller may edit. Status is always the row the worker last wrote, never a guess.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, Literal

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from groundtruth.platform.api.errors import ApiErrorBody
from groundtruth.platform.api.scope import audit
from groundtruth.platform.auth.authz import Action, Capability, ProjectAccess, require_project
from groundtruth.platform.auth.deps import resolve_sessions
from groundtruth.platform.auth.service import auth_error
from groundtruth.platform.config import get_settings
from groundtruth.platform.projects import ingestion
from groundtruth.platform.store.models import ObservationIngestionRow

router = APIRouter(tags=["project-observations"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ApiErrorBody, "description": "Not signed in."},
    403: {"model": ApiErrorBody, "description": "Your access level or role does not allow this."},
    404: {"model": ApiErrorBody, "description": "Unknown project or ingestion."},
    409: {"model": ApiErrorBody, "description": "An ingestion is already queued or running."},
    422: {"model": ApiErrorBody, "description": "The request cannot be accepted."},
    503: {"model": ApiErrorBody, "description": "No database, or ingestion is switched off."},
}

Viewer = Annotated[ProjectAccess, Depends(require_project(Capability.OVERVIEW))]
Editor = Annotated[
    ProjectAccess, Depends(require_project(Capability.EDIT, action=Action.EDIT_PROJECT))
]

WAITING_HINT_AFTER_SECONDS = 300

IngestionStatus = Literal["queued", "running", "succeeded", "partial", "failed", "cancelled"]
YearState = Literal["observed", "partial_coverage", "no_usable_data"]


class IngestionRequest(BaseModel):
    """What to ingest. Every field has a default, and the server re-validates all of them."""

    start_year: int = Field(description="First calendar year (Sentinel-2 L2A starts in 2017).")
    end_year: int | None = Field(default=None, description="Last year; defaults to start_year.")
    window_start: str = Field(default="06-01", description="Season start, MM-DD.")
    window_end: str = Field(default="06-30", description="Season end, MM-DD (same calendar year).")
    max_cloud_cover: float = Field(default=25.0, description="Scene cloud cover limit, percent.")
    indicators: list[str] | None = Field(
        default=None, description="Subset of ndvi, evi, ndmi, nbr. NDVI is always stored."
    )
    resolution_m: float = Field(default=100.0, description="Analysis grid size in metres.")
    max_scenes_per_year: int = Field(default=3, description="Scenes combined per year.")


class IngestionParamsView(BaseModel):
    start_year: int
    end_year: int
    window_start: str
    window_end: str
    max_cloud_cover: float
    indicators: list[str]
    resolution_m: float
    max_scenes_per_year: int
    platform: str = "sentinel-2"


class IngestionYearView(BaseModel):
    year: int
    state: YearState = Field(
        description="observed: value and coverage ok; partial_coverage: value exists but the "
        "area is not fully covered; no_usable_data: left empty, never estimated."
    )
    n_scenes: int | None = None
    scene_ids: list[str] = []
    acquisition_dates: list[str] = []
    contributing_tiles: list[str] = []
    aoi_coverage_pct: float | None = None
    clear_pixel_fraction: float | None = None
    is_spatially_complete: bool | None = None
    values: dict[str, float | None] = {}


class IngestionCoverageView(BaseModel):
    threshold_pct: float
    complete_years: list[int]
    partial_years: list[int]
    years_without_data: list[int]


class StoredBundleView(BaseModel):
    file: str
    sha256: str


class IngestionResultView(BaseModel):
    catalog_url: str | None = None
    platform: str | None = None
    collection: str | None = None
    bbox: list[float] = []
    years_requested: list[int] = []
    years: list[IngestionYearView] = []
    coverage: IngestionCoverageView | None = None
    stored_bundles: dict[str, StoredBundleView] = {}
    limitations: list[str] = []
    code_version: str | None = None
    method: str | None = None


class IngestionView(BaseModel):
    id: str
    project_id: str
    status: IngestionStatus
    status_detail: str | None
    error_code: str | None
    params: IngestionParamsView
    requested_by: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    age_seconds: int = Field(description="Seconds since the request was made (or finished).")
    waiting_hint: str | None = Field(
        default=None, description="Set when a queued request has waited unusually long."
    )
    result: IngestionResultView | None
    ledger_record_id: str | None


class IngestionLimitsView(BaseModel):
    first_year: int
    last_year: int
    max_years: int
    max_total_scenes: int
    min_resolution_m: float
    max_resolution_m: float
    max_grid_pixels: int
    coverage_threshold_pct: float
    indicators: list[str]
    default_indicators: list[str]


class IngestionListView(BaseModel):
    project_id: str
    enabled: bool
    active: bool = Field(description="True while a request is queued or running.")
    limits: IngestionLimitsView
    ingestions: list[IngestionView]
    explanation: str


EXPLANATION = (
    "Requests are processed by the GroundTruth worker, not by this page. Sentinel-2 scenes are "
    "downloaded for your boundary, cloud-masked and reduced to one value per year. Years that "
    "cannot be measured stay empty and are never estimated, and partial coverage is reported as "
    "partial."
)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def _view(row: ObservationIngestionRow) -> IngestionView:
    created = _aware(row.created_at) or datetime.now(UTC)
    finished = _aware(row.finished_at)
    ref = finished or datetime.now(UTC)
    age = max(int((ref - created).total_seconds()), 0)
    hint = None
    if row.status == "queued" and age > WAITING_HINT_AFTER_SECONDS:
        hint = (
            f"This request has been waiting {age // 60} minutes. No worker has picked it up; "
            "ask your operator whether the GroundTruth worker is running."
        )
    params = dict(row.params or {})
    params.setdefault("end_year", params.get("start_year"))
    return IngestionView(
        id=row.id,
        project_id=row.project_id,
        status=row.status,  # type: ignore[arg-type]
        status_detail=row.status_detail,
        error_code=row.error_code,
        params=IngestionParamsView(**params),
        requested_by=row.requested_by,
        created_at=created,
        started_at=_aware(row.started_at),
        finished_at=finished,
        age_seconds=age,
        waiting_hint=hint,
        result=IngestionResultView(**row.result) if row.result else None,
        ledger_record_id=row.ledger_record_id,
    )


def _reject(exc: ingestion.IngestionRequestError) -> HTTPException:
    status = {ingestion.E_BUSY: 409, ingestion.E_DISABLED: 503}.get(exc.code, 422)
    return HTTPException(
        status_code=status,
        detail={"code": exc.code, "message": exc.message, "hint": exc.hint},
    )


@router.get(
    "/projects/{project_id}/observations/ingestions",
    response_model=IngestionListView,
    summary="Observation ingestion requests for a project, newest first",
    responses=_ERRORS,
)
def list_ingestions(request: Request, access: Viewer) -> IngestionListView:
    with resolve_sessions(request)() as db:
        rows = (
            db.execute(
                sa.select(ObservationIngestionRow)
                .where(ObservationIngestionRow.project_id == access.project.id)
                .order_by(ObservationIngestionRow.created_at.desc())
                .limit(20)
            )
            .scalars()
            .all()
        )
        views = [_view(r) for r in rows]
    return IngestionListView(
        project_id=access.project.id,
        enabled=get_settings().observation_ingestion_enabled,
        active=any(v.status in ingestion.ACTIVE_STATUSES for v in views),
        limits=IngestionLimitsView(**ingestion.limits()),
        ingestions=views,
        explanation=EXPLANATION,
    )


@router.post(
    "/projects/{project_id}/observations/ingestions",
    response_model=IngestionView,
    status_code=202,
    summary="Request satellite observations for the project boundary",
    responses=_ERRORS,
)
def request_ingestion(body: IngestionRequest, request: Request, access: Editor) -> IngestionView:
    raw = body.model_dump()
    raw["end_year"] = body.end_year if body.end_year is not None else body.start_year
    with resolve_sessions(request)() as db:
        from groundtruth.platform.store.models import ProjectRow

        project = db.get(ProjectRow, access.project.id)
        if project is None:
            raise auth_error("not_found", "Project not found.")
        try:
            row = ingestion.enqueue(db, project, access.ctx.user_id, raw)
        except ingestion.IngestionRequestError as exc:
            raise _reject(exc) from exc
        db.commit()
        view = _view(row)
    audit(
        request,
        access.ctx,
        action="observations.ingest_requested",
        resource_type="project",
        resource_id=access.project.id,
        details={"ingestion_id": view.id, **view.params.model_dump()},
    )
    return view


@router.get(
    "/projects/{project_id}/observations/ingestions/{ingestion_id}",
    response_model=IngestionView,
    summary="One ingestion request",
    responses=_ERRORS,
)
def get_ingestion(ingestion_id: str, request: Request, access: Viewer) -> IngestionView:
    with resolve_sessions(request)() as db:
        row = db.get(ObservationIngestionRow, ingestion_id)
        # An ingestion of another project is reported exactly like a missing one.
        if row is None or row.project_id != access.project.id:
            raise auth_error("not_found", "Ingestion not found.")
        return _view(row)


@router.post(
    "/projects/{project_id}/observations/ingestions/{ingestion_id}/cancel",
    response_model=IngestionView,
    summary="Cancel a request that has not started",
    responses=_ERRORS,
)
def cancel_ingestion(ingestion_id: str, request: Request, access: Editor) -> IngestionView:
    with resolve_sessions(request)() as db:
        row = db.get(ObservationIngestionRow, ingestion_id)
        if row is None or row.project_id != access.project.id:
            raise auth_error("not_found", "Ingestion not found.")
        if not ingestion.cancel_queued(db, row):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "cannot_cancel",
                    "message": "Only a request that has not started can be cancelled.",
                    "hint": "A running request cannot be interrupted safely; wait for it to finish.",
                },
            )
        db.commit()
        view = _view(row)
    audit(
        request,
        access.ctx,
        action="observations.ingest_cancelled",
        resource_type="project",
        resource_id=access.project.id,
        details={"ingestion_id": ingestion_id},
    )
    return view
