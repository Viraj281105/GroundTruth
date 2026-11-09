"""Project routes: list an organization's projects, create one with a boundary, read one.

Creation is multipart (fields plus the ``boundary`` file). The boundary is validated before
anything is written, so a rejected upload leaves no row and no file.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from groundtruth.platform.api.dependencies import get_store, store_errors
from groundtruth.platform.api.errors import ApiErrorBody
from groundtruth.platform.api.org_schemas import GrantRequest, GrantView
from groundtruth.platform.api.project_schemas import (
    AssessmentView,
    ClimateView,
    EvidenceInventoryView,
    Indicator,
    ObservationsView,
    ReadinessBody,
    ReadinessView,
    VerificationView,
)
from groundtruth.platform.api.schemas import SIMULATED_NOTICE, ProjectView
from groundtruth.platform.api.scope import audit
from groundtruth.platform.audit.ledger import AuditLedger
from groundtruth.platform.audit.service import record_event
from groundtruth.platform.auth.authz import (
    AccessContext,
    Action,
    Capability,
    ProjectAccess,
    ProjectLevel,
    require_org_action,
    require_project,
)
from groundtruth.platform.auth.deps import resolve_sessions
from groundtruth.platform.auth.service import auth_error
from groundtruth.platform.config import get_settings
from groundtruth.platform.projects import documents as documents_service
from groundtruth.platform.projects import service, views
from groundtruth.platform.projects.assessment import build_project_assessment
from groundtruth.platform.projects.boundary import (
    MAX_BOUNDARY_BYTES,
    BoundaryValidationError,
    parse_boundary,
)
from groundtruth.platform.projects.readiness import _boundary_file, compute_project_readiness
from groundtruth.platform.projects.redaction import redact
from groundtruth.platform.reports.dossier import build_dossier
from groundtruth.platform.store.interface import EvidenceStore, RunFilter
from groundtruth.platform.store.models import OrganizationRow, ProjectRow

router = APIRouter(tags=["projects"])
_log = logging.getLogger(__name__)


class ProjectUploadForm(BaseModel):
    """The multipart fields of project creation (a named model keeps the OpenAPI name plain)."""

    boundary: UploadFile = Field(description="Project boundary (.geojson, .json, .kml).")
    name: str = Field(min_length=1, max_length=200)
    country: str = Field(min_length=1, max_length=100)
    ecosystem: str = Field(min_length=1, max_length=100)
    intervention: str = Field(min_length=1, max_length=100)
    treatment_start_year: int = Field(ge=1970, le=max(datetime.now().year + 1, 2100))


_ERRORS = {
    401: {"model": ApiErrorBody, "description": "Not signed in."},
    403: {"model": ApiErrorBody, "description": "Your role or access level does not allow this."},
    404: {"model": ApiErrorBody, "description": "Unknown organization or project."},
    422: {"model": ApiErrorBody, "description": "Invalid fields or boundary file."},
    503: {"model": ApiErrorBody, "description": "No database is configured."},
}

Viewer = Annotated[AccessContext, Depends(require_org_action(Action.VIEW_ORG))]
Creator = Annotated[AccessContext, Depends(require_org_action(Action.CREATE_PROJECT))]
Reader = Annotated[ProjectAccess, Depends(require_project(Capability.OVERVIEW))]
SeriesReader = Annotated[ProjectAccess, Depends(require_project(Capability.SERIES))]
Store = Annotated[EvidenceStore, Depends(get_store)]
GrantManager = Annotated[
    ProjectAccess, Depends(require_project(Capability.EDIT, action=Action.MANAGE_GRANTS))
]
DossierExporter = Annotated[ProjectAccess, Depends(require_project(Capability.DOSSIER_EXPORT))]


def project_views(db: Session, items: list[tuple[ProjectRow, ProjectLevel]]) -> list[ProjectView]:
    org_ids = {p.organization_id for p, _ in items}
    owners = {
        o.id: o
        for o in db.execute(select(OrganizationRow).where(OrganizationRow.id.in_(org_ids)))
        .scalars()
        .all()
    }
    return [
        ProjectView(
            id=p.id,
            slug=p.slug,
            name=p.name,
            country=p.country,
            ecosystem=p.ecosystem,
            intervention=p.intervention,
            treatment_start_year=p.treatment_start_year,
            data_mode=p.data_mode,  # type: ignore[arg-type]
            owner_slug=owners[p.organization_id].slug,
            owner_name=owners[p.organization_id].name,
            access_level=level.value,  # type: ignore[arg-type]
            boundary_sha256=p.boundary_sha256,
            reported_funding_amount=(
                float(p.reported_funding_amount) if p.reported_funding_amount is not None else None
            ),
            reported_funding_currency=p.reported_funding_currency,
            created_at=p.created_at,
        )
        for p, level in items
    ]


@router.get(
    "/orgs/{slug}/projects",
    response_model=list[ProjectView],
    summary="Projects the organization owns or has been granted",
    responses={401: _ERRORS[401], 403: _ERRORS[403], 404: _ERRORS[404], 503: _ERRORS[503]},
)
def list_projects(request: Request, ctx: Viewer) -> list[ProjectView]:
    with resolve_sessions(request)() as db:
        return project_views(db, service.list_org_projects(db, ctx))


@router.post(
    "/orgs/{slug}/projects",
    response_model=ProjectView,
    status_code=201,
    summary="Create a project from a boundary file (GeoJSON or KML, max 5 MB)",
    responses={
        401: _ERRORS[401],
        403: _ERRORS[403],
        404: _ERRORS[404],
        422: _ERRORS[422],
        503: _ERRORS[503],
    },
)
def create_project(
    request: Request,
    ctx: Creator,
    form: Annotated[ProjectUploadForm, Form()],
) -> ProjectView:
    boundary = form.boundary
    name, country, ecosystem = form.name, form.country, form.ecosystem
    intervention, treatment_start_year = form.intervention, form.treatment_start_year
    raw = boundary.file.read(MAX_BOUNDARY_BYTES + 1)
    try:
        parsed = parse_boundary(raw, boundary.filename or "")
    except BoundaryValidationError as exc:
        raise auth_error("invalid_boundary", str(exc)) from exc
    with resolve_sessions(request)() as db:
        row = service.create_project(
            db,
            ctx,
            name=name,
            country=country,
            ecosystem=ecosystem,
            intervention=intervention,
            treatment_start_year=treatment_start_year,
            boundary=parsed,
            request=request,
        )
        db.commit()
        return project_views(db, [(row, ProjectLevel.OWNER)])[0]


@router.get(
    "/projects/{project_id}",
    response_model=ProjectView,
    summary="One project by id or slug",
    responses={401: _ERRORS[401], 403: _ERRORS[403], 404: _ERRORS[404], 503: _ERRORS[503]},
)
def get_project(request: Request, access: Reader) -> ProjectView:
    with resolve_sessions(request)() as db:
        project = service.get_project(db, access.project.id)
        assert project is not None
        return project_views(db, [(project, access.level)])[0]


# --- project data -----------------------------------------------------------------------------
#
# Every route below resolves the project through ``require_project`` (404 for no access, 403 for
# too low a level) and answers 200 with ``status: "unavailable"`` and the loader's reason when
# the data is absent or fails its provenance check. Level-dependent fields are removed, never
# nulled, by ``redact``; the models mark them with ``min_level``.

_DATA_ERRORS: dict[int | str, dict[str, Any]] = {
    401: _ERRORS[401],
    403: _ERRORS[403],
    404: _ERRORS[404],
    503: _ERRORS[503],
}


def _fresh(request: Request, access: ProjectAccess) -> ProjectRow:
    """The project re-read in its own session (the authorization copy is detached)."""
    with resolve_sessions(request)() as db:
        project = service.get_project(db, access.project.id)
        if project is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "not_found", "message": "Project not found.", "hint": None},
            )
        db.expunge(project)
        return project


def _respond(model: Any, access: ProjectAccess) -> JSONResponse:
    return JSONResponse(jsonable_encoder(redact(model, access.level)))


@router.get(
    "/projects/{project_id}/readiness",
    summary="Computed readiness: can causal attribution be attempted?",
    responses={200: {"model": ReadinessView}, **_DATA_ERRORS},
)
def get_readiness(request: Request, access: Reader) -> JSONResponse:
    project = _fresh(request, access)
    view = views.build_readiness(project, access.level.value, get_settings().data_dir)
    return _respond(view, access)


@router.get(
    "/projects/{project_id}/observations",
    summary="Annual observations of one vegetation index",
    responses={200: {"model": ObservationsView}, **_DATA_ERRORS, 422: _ERRORS[422]},
)
def get_observations(
    request: Request,
    access: SeriesReader,
    indicator: Annotated[Indicator, Query(description="ndvi, evi, ndmi or nbr.")] = "ndvi",
) -> JSONResponse:
    """Scene ids and checksums appear only for levels with full evidence access."""
    project = _fresh(request, access)
    view = views.build_observations(project, indicator, access.level.value, get_settings().data_dir)
    return _respond(view, access)


@router.get(
    "/projects/{project_id}/climate",
    summary="Annual climate series for the project",
    responses={200: {"model": ClimateView}, **_DATA_ERRORS},
)
def get_climate(request: Request, access: SeriesReader) -> JSONResponse:
    project = _fresh(request, access)
    view = views.build_climate(project, access.level.value, get_settings().data_dir)
    return _respond(view, access)


@router.get(
    "/projects/{project_id}/evidence-inventory",
    summary="What evidence exists for the project",
    responses={200: {"model": EvidenceInventoryView}, **_DATA_ERRORS},
)
def get_evidence_inventory(request: Request, access: Reader) -> JSONResponse:
    """Counts, kinds, states and sources for everyone; checksums, scene ids and the item list
    only for levels that hold full evidence access (a `view` grant gets the summary)."""
    project = _fresh(request, access)
    with resolve_sessions(request)() as db:
        documents = [
            documents_service.document_dict(r)
            for r in documents_service.list_documents(db, project.id)
        ]
    view = views.build_inventory(project, access.level.value, get_settings().data_dir, documents)
    return _respond(view, access)


_MAX_RUN_PAGES = 10


def _latest_completed(
    store: EvidenceStore, project_id: str, *, allow_simulated: bool
) -> str | None:
    """Run id of the newest finished run filed under the project whose engine completed.

    An observed project never serves a simulated run (R7): those are skipped.
    """
    after = None
    for _ in range(_MAX_RUN_PAGES):
        page = store.list_runs(
            RunFilter(project_ids=(project_id,), statuses=("succeeded",)), limit=50, after=after
        )
        for summary in page.items:
            if summary.engine_status == "completed" and (
                allow_simulated or not summary.is_simulated
            ):
                return summary.run_id
        if page.next_cursor is None:
            return None
        after = page.next_cursor
    return None


@router.get(
    "/projects/{project_id}/verification",
    summary="Latest completed verification run, or not_estimable",
    responses={200: {"model": VerificationView}, **_DATA_ERRORS},
)
def get_verification(request: Request, access: Reader, store: Store) -> JSONResponse:
    """The newest completed run for the project. With none, `status` is `not_estimable` and
    `readiness` says why. A simulated project or run is labelled `simulated` with the
    SIMULATED DATA warning. The evidence bundle and spec hash need diagnostics access."""
    project = _fresh(request, access)
    readiness = ReadinessBody(
        **views.readiness_fields(
            compute_project_readiness(project, data_dir=get_settings().data_dir)
        )
    )
    with store_errors():
        run_id = _latest_completed(
            store, project.id, allow_simulated=views.data_mode_of(project) == "simulated"
        )
        result = store.by_run_id(run_id) if run_id else None
        summary = store.summary_for(run_id) if run_id else None
    bundle = result.bundle if result else None
    simulated = views.data_mode_of(project) == "simulated" or bool(result and result.is_simulated)
    warnings = list(bundle.warnings) if bundle else []
    if simulated and not any("SIMULATED DATA" in w for w in warnings):
        warnings.insert(0, SIMULATED_NOTICE)
    verdict = bundle.verdict if bundle else None
    view = VerificationView(
        data_mode="simulated" if simulated else "observed",
        access_level=access.level.value,  # type: ignore[arg-type]
        status="completed" if result else "not_estimable",
        readiness=readiness,
        warnings=warnings,
        is_simulated=simulated,
        run_id=result.run_id if result else None,
        case_id=result.case_id if result else None,
        verdict_label=summary.verdict_label if summary else None,
        verdict_rationale=verdict.rationale if verdict else None,
        caveats=list(verdict.caveats) if verdict else [],
        engine_version=result.engine.engine_version if result else None,
        created_at=summary.created_at if summary else None,
        spec_hash=result.spec_hash if result else None,
        bundle=bundle,
    )
    return _respond(view, access)


@router.get(
    "/projects/{project_id}/assessment",
    summary="The eight-dimension assessment of the project",
    responses={200: {"model": AssessmentView}, **_DATA_ERRORS},
)
def get_assessment(request: Request, access: Reader) -> JSONResponse:
    """Serializes the engine assessment built from the project's real artifacts. Each
    dimension carries `status_kind` so `status` is never ambiguous. References into causal
    diagnostics (`diagnostic_refs`) need diagnostics access; values are never altered."""
    project = _fresh(request, access)
    assessment = build_project_assessment(project, data_dir=get_settings().data_dir)
    return _respond(views.build_assessment(assessment, project, access.level.value), access)


_GEOJSON = "application/geo+json"


def _feature_collection(
    project: ProjectRow, access: ProjectAccess, features: list[Any]
) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "features": features,
        "data_mode": views.data_mode_of(project),
        "access_level": access.level.value,
    }


@router.get(
    "/projects/{project_id}/boundary.geojson",
    summary="The project boundary as GeoJSON",
    responses={
        200: {"content": {_GEOJSON: {"schema": {"type": "object"}}}, "description": "Boundary."},
        **_DATA_ERRORS,
    },
)
def get_boundary(request: Request, access: Reader) -> JSONResponse:
    """The stored boundary with `data_mode` and `access_level` as foreign members."""
    project = _fresh(request, access)
    file = _boundary_file(project.boundary_path) if project.boundary_path else None
    unavailable = HTTPException(
        status_code=404,
        detail={
            "code": "boundary_unavailable",
            "message": "This project has no readable boundary file.",
            "hint": "Upload the boundary again.",
        },
    )
    if file is None:
        raise unavailable
    try:
        doc = json.loads(file.read_text(encoding="utf-8"))
        if doc.get("type") == "FeatureCollection":
            features = list(doc["features"])
        elif doc.get("type") == "Feature":
            features = [doc]
        else:
            features = [{"type": "Feature", "properties": {}, "geometry": doc}]
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise unavailable from exc
    return JSONResponse(_feature_collection(project, access, features), media_type=_GEOJSON)


@router.get(
    "/projects/{project_id}/donors.geojson",
    summary="Screened donor regions for the project, if any",
    responses={
        200: {"content": {_GEOJSON: {"schema": {"type": "object"}}}, "description": "Donors."},
        **_DATA_ERRORS,
    },
)
def get_donors(request: Request, access: Reader) -> JSONResponse:
    """The donor features screened for this project's case. A project without a screening
    file answers 200 with an empty FeatureCollection and the header `X-GT-Available: false`
    (`true` otherwise); there is no 404 and no invented donor."""
    project = _fresh(request, access)
    features: list[Any] = []
    cases = get_settings().cases_dir / "boundaries"
    if project.case_id and cases.is_dir():
        for file in sorted(cases.glob("*-donors.geojson")):
            try:
                doc = json.loads(file.read_text(encoding="utf-8"))
                features.extend(
                    f
                    for f in doc["features"]
                    if f.get("properties", {}).get("case_id") == project.case_id
                )
            except (OSError, ValueError, KeyError, TypeError, AttributeError):
                continue
    return JSONResponse(
        _feature_collection(project, access, features),
        media_type=_GEOJSON,
        headers={"X-GT-Available": "true" if features else "false"},
    )


# --- grants -----------------------------------------------------------------------------------
#
# Only the owning organization manages grants (``EDIT`` is owner level, plus the
# ``MANAGE_GRANTS`` role gate). A revoked grant keeps its row for the audit trail; granting again
# reactivates it. Every change is audited with the grantee's slug and the level.


def _grant_view(grant: Any, org: OrganizationRow) -> GrantView:
    return GrantView(
        org_slug=org.slug,
        org_name=org.name,
        org_type=org.type,
        level=grant.level,
        granted_at=grant.created_at,
    )


def _grantee(db: Session, slug: str) -> OrganizationRow:
    org = db.execute(
        select(OrganizationRow).where(OrganizationRow.slug == slug)
    ).scalar_one_or_none()
    if org is None:
        raise auth_error("not_found", "Organization not found.")
    return org


_GRANT_ERRORS: dict[int | str, dict[str, Any]] = {
    401: _ERRORS[401],
    403: _ERRORS[403],
    404: _ERRORS[404],
    409: {"model": ApiErrorBody, "description": "A concurrent change conflicted; retry."},
    422: _ERRORS[422],
    503: _ERRORS[503],
}


@router.get(
    "/projects/{project_id}/grants",
    response_model=list[GrantView],
    summary="Organizations the project is currently granted to",
    responses=_GRANT_ERRORS,
)
def list_grants(request: Request, access: GrantManager) -> list[GrantView]:
    with resolve_sessions(request)() as db:
        return [_grant_view(g, o) for g, o in service.active_grants(db, access.project.id)]


@router.post(
    "/projects/{project_id}/grants",
    response_model=GrantView,
    status_code=201,
    summary="Grant another organization access to the project",
    responses=_GRANT_ERRORS,
)
def create_grant(body: GrantRequest, request: Request, access: GrantManager) -> GrantView:
    """Creates the grant, or reactivates a revoked one (with the new level)."""
    with resolve_sessions(request)() as db:
        grantee = _grantee(db, body.org_slug)
        if grantee.id == access.project.organization_id:
            raise auth_error("invalid_grant", "The owning organization already has full access.")
        project = service.get_project(db, access.project.id)
        assert project is not None
        try:
            grant = service.grant_project(
                db, project, grantee, body.level, actor_user_id=access.ctx.user_id
            )
        except IntegrityError as exc:
            db.rollback()
            raise auth_error("conflict", "The grant changed concurrently; retry.") from exc
        record_event(
            db,
            action="project.grant",
            outcome="success",
            actor_user_id=access.ctx.user_id,
            organization_id=access.ctx.org_id,
            resource_type="project",
            resource_id=project.id,
            request=request,
            details={"grantee": grantee.slug, "level": body.level},
        )
        db.commit()
        return _grant_view(grant, grantee)


@router.delete(
    "/projects/{project_id}/grants/{org_slug}",
    status_code=204,
    summary="Revoke an organization's access to the project",
    responses=_GRANT_ERRORS,
)
def revoke_grant(org_slug: str, request: Request, access: GrantManager) -> Response:
    """Sets ``revoked_at``; the grantee loses access on its next request."""
    with resolve_sessions(request)() as db:
        grantee = _grantee(db, org_slug)
        project = service.get_project(db, access.project.id)
        assert project is not None
        grant = service.revoke_project_grant(db, project, grantee)
        if grant is None:
            raise auth_error("not_found", "No active grant for that organization.")
        record_event(
            db,
            action="project.revoke",
            outcome="success",
            actor_user_id=access.ctx.user_id,
            organization_id=access.ctx.org_id,
            resource_type="project",
            resource_id=project.id,
            request=request,
            details={"grantee": grantee.slug, "level": grant.level},
        )
        db.commit()
    return Response(status_code=204)


# --- dossier ----------------------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/export/dossier",
    summary="Technical dossier (ZIP) for audit",
    responses={
        200: {"content": {"application/zip": {"schema": {"type": "string", "format": "binary"}}}},
        401: _ERRORS[401],
        403: _ERRORS[403],
        404: _ERRORS[404],
        503: _ERRORS[503],
    },
)
def export_dossier(request: Request, access: DossierExporter) -> Response:
    """README with limitations, readiness, evidence inventory, assessment, observations, climate,
    provenance and a sha256 manifest. Owner and audit levels only; the download is audited."""
    project = _fresh(request, access)
    with resolve_sessions(request)() as db:
        documents = [
            documents_service.document_dict(r)
            for r in documents_service.list_documents(db, project.id)
        ]
    content = build_dossier(project, data_dir=get_settings().data_dir, documents=documents)
    headers = {
        "Content-Disposition": f'attachment; filename="{project.slug}-dossier.zip"',
        "X-GroundTruth-Data-Mode": views.data_mode_of(project),
    }
    # Bind the exact bytes to the ledger. If sealing fails the file is still delivered, but
    # without seal headers and with an explicit "unsealed" marker: a download is never
    # described as sealed unless a record really exists.
    seal_details: dict[str, Any] = {}
    try:
        ledger = AuditLedger(resolve_sessions(request))
        record = ledger.record_report_seal(
            project.id,
            report_kind="technical_dossier",
            content=content,
            boundary_geometry_hash=f"sha256:{project.boundary_sha256}"
            if project.boundary_sha256
            else "unrecorded",
            details={"data_mode": views.data_mode_of(project)},
        )
        verification = ledger.verify_project(project.id)
        headers.update(
            {
                "X-GroundTruth-Ledger-Record": record.record_id,
                "X-GroundTruth-Ledger-Sequence": str(record.sequence),
                "X-GroundTruth-Ledger-Root": verification.ledger_root or "",
                "X-GroundTruth-Report-SHA256": record.input_files_hashes["technical_dossier"],
            }
        )
        seal_details = {"ledger_record_id": record.record_id}
    except Exception:
        _log.exception("could not seal dossier for project %s", project.id)
        headers["X-GroundTruth-Ledger"] = "unsealed"
    audit(
        request,
        access.ctx,
        action="export.download",
        resource_type="project",
        resource_id=project.id,
        details={"format": "dossier", **seal_details},
    )
    return Response(content=content, media_type="application/zip", headers=headers)
