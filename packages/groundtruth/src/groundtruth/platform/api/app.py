"""FastAPI application exposing the verification pipeline.

**Owner: Bhumi.**

This module talks to the engine through exactly three names — ``run_analysis``,
``describe_engine`` and ``ENGINE_VERSION`` — and otherwise knows nothing about
how an analysis is computed. Swapping the estimator, the solver or the whole
engine internals requires no change here.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from groundtruth import __version__
from groundtruth.contracts import CONTRACT_VERSION
from groundtruth.contracts.errors import CaseDefinitionError, DataUnavailableError
from groundtruth.contracts.result import AnalysisResult, EngineStatus, ErrorCode
from groundtruth.engine import ENGINE_VERSION, describe_engine, run_analysis
from groundtruth.observability import setup_telemetry
from groundtruth.platform.api.auth import router as auth_router
from groundtruth.platform.api.claims import router as claims_router
from groundtruth.platform.api.events import router as events_router
from groundtruth.platform.api.exports import router as exports_router
from groundtruth.platform.api.jobs import router as jobs_router
from groundtruth.platform.api.openapi_schema import install_openapi
from groundtruth.platform.api.runs import router as runs_router
from groundtruth.platform.api.schemas import (
    CaseDetail,
    CaseSummary,
    CreateCaseRequest,
    EngineFailureBody,
    HealthResponse,
    MessageErrorBody,
    VerificationRequest,
    VerificationResponse,
)
from groundtruth.platform.api.tiles import router as tiles_router
from groundtruth.platform.auth.csrf import CsrfOriginMiddleware
from groundtruth.platform.auth.deps import require_role
from groundtruth.platform.cases.creator import create_and_register_case
from groundtruth.platform.cases.registry import get_case, load_all_cases
from groundtruth.platform.config import get_settings
from groundtruth.platform.datasets.access import earth_engine_access, synthetic_access
from groundtruth.platform.reports.narrative import generate_report

_log = logging.getLogger("groundtruth.auth")


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    if not get_settings().auth_required:
        _log.warning(
            "AUTH_REQUIRED is false: starting/cancelling analyses and the claims workbench "
            "are open to anyone who can reach this API. Set AUTH_REQUIRED=true for any "
            "shared deployment."
        )
    yield


app = FastAPI(
    lifespan=_lifespan,
    title="GroundTruth",
    version=__version__,
    description=(
        "Independent causal verification for climate restoration and carbon-credit claims. "
        "This API returns evidence bundles with full provenance, not bare scores. A divergence "
        "between an independent estimate and a developer claim is a trigger for accredited "
        "review, never a finding of fraud."
    ),
)

setup_telemetry(app)  # no-op unless OpenTelemetry is installed and an endpoint is set

# Added before CORS so CORS is outermost and a rejected request still carries CORS headers.
app.add_middleware(CsrfOriginMiddleware, allowed_origins=lambda: get_settings().cors_origins)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["*"],
)

# Stored-run endpoints (issue #35). They read the evidence store lazily, so the endpoints
# below keep working with no database configured.
app.include_router(runs_router)
app.include_router(jobs_router)
app.include_router(events_router)
app.include_router(tiles_router)
app.include_router(claims_router)
app.include_router(auth_router)
app.include_router(exports_router, include_in_schema=False)

# The frontend's TypeScript types are generated from this schema (issue #17); the served
# /openapi.json and the committed snapshot are built by the same function.
install_openapi(app)


def _either(*schemas: str) -> dict[str, Any]:
    """An OpenAPI response body that may be any one of the named schemas."""
    refs = [{"$ref": f"#/components/schemas/{name}"} for name in schemas]
    return {"application/json": {"schema": {"anyOf": refs}}}


_ENGINE_FAILURE = {"model": EngineFailureBody}

ERROR_STATUS: dict[ErrorCode, int] = {
    ErrorCode.INVALID_REQUEST: 422,
    ErrorCode.CONTRACT_VERSION_MISMATCH: 409,
    ErrorCode.DATA_UNAVAILABLE: 503,
    ErrorCode.INSUFFICIENT_DATA: 422,
    ErrorCode.DONOR_POOL_INADEQUATE: 422,
    ErrorCode.ESTIMATION_FAILED: 500,
    ErrorCode.NOT_IMPLEMENTED: 501,
    ErrorCode.INTERNAL_ERROR: 500,
}
"""Maps contract error codes to HTTP status. The UI reads the code, not the prose."""


def _summary(case_id: str) -> CaseSummary:
    case = get_case(case_id)
    return CaseSummary(
        case_id=case.case_id,
        name=case.claim.name,
        country=case.claim.country,
        standard=case.claim.standard.value,
        registry_id=case.claim.registry_id,
        ecosystem=case.ecosystem,
        indicator=case.indicator.value,
        pre_period=f"{case.window.pre_start}-{case.window.pre_end}",
        post_period=f"{case.window.post_start}-{case.window.post_end}",
        status=case.status,
        has_known_reference=bool(case.known_reference),
    )


@app.get("/health", response_model=HealthResponse, tags=["meta"])
def health() -> HealthResponse:
    """Liveness and honest capability reporting."""
    capabilities = describe_engine()
    return HealthResponse(
        version=__version__,
        engine_version=ENGINE_VERSION,
        contract_version=CONTRACT_VERSION,
        earth_observation_implemented=False,
        genai_narration_implemented=False,
        cases_available=len(load_all_cases()),
        engine_capabilities=capabilities["implemented"],
    )


@app.get("/cases", response_model=list[CaseSummary], tags=["cases"])
def list_case_summaries() -> list[CaseSummary]:
    """List every case definition."""
    return [_summary(cid) for cid in load_all_cases()]


@app.get(
    "/cases/{case_id}",
    response_model=CaseDetail,
    tags=["cases"],
    responses={404: {"model": MessageErrorBody, "description": "Unknown case."}},
)
def get_case_detail(case_id: str) -> CaseDetail:
    """Return one case definition in full."""
    try:
        case = get_case(case_id)
    except CaseDefinitionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    base = _summary(case_id)
    return CaseDetail(
        **base.model_dump(),
        area_ha=case.claim.project_area_ha,
        donor_search_region=case.donor_search_region.strip(),
        donor_pool_size=case.donor_pool_size,
        covariates=list(case.covariates),
        known_reference=case.known_reference,
        notes=case.notes.strip(),
    )


@app.post(
    "/cases",
    response_model=CaseDetail,
    tags=["cases"],
    dependencies=[Depends(require_role("user"))],
)
def create_case(body: CreateCaseRequest) -> CaseDetail:
    """Create, calibrate and register a new project case."""
    case = create_and_register_case(
        name=body.name,
        country=body.country,
        ecosystem=body.ecosystem,
        standard=body.standard,
        registry_id=body.registry_id,
        area_ha=body.area_ha,
        crediting_period_start=body.crediting_period_start,
        crediting_period_end=body.crediting_period_end,
        claimed_credits_tco2e=body.claimed_credits_tco2e,
        indicator=body.indicator,
        donor_pool_size=body.donor_pool_size,
        pre_start=body.pre_start,
        pre_end=body.pre_end,
        post_start=body.post_start,
        post_end=body.post_end,
        boundary_geojson=body.boundary_geojson,
        custom_case_id=body.case_id,
    )
    return get_case_detail(case.case_id)


@app.post(
    "/cases/{case_id}/verify",
    response_model=VerificationResponse,
    tags=["verification"],
    dependencies=[Depends(require_role("user"))],
    responses={
        404: {"model": MessageErrorBody, "description": "Unknown case."},
        409: {**_ENGINE_FAILURE, "description": "Unsupported contract version."},
        # 422 means two different things here, and both are documented, not one or other.
        422: {
            "description": "Either the request body is invalid (a validation error), or the "
            "engine refused or rejected the request (an engine failure, where `is_refusal` "
            "says which). A refusal is a legitimate outcome, not a malfunction.",
            "content": _either("HTTPValidationError", "EngineFailureBody"),
        },
        500: {**_ENGINE_FAILURE, "description": "The engine failed to estimate."},
        501: {
            "description": "Not implemented: observed data (a plain message), or a capability "
            "the engine does not have (an engine failure).",
            "content": _either("MessageErrorBody", "EngineFailureBody"),
        },
        503: {**_ENGINE_FAILURE, "description": "A required dataset could not be retrieved."},
    },
)
def verify(case_id: str, request: VerificationRequest) -> VerificationResponse:
    """Run the verification pipeline for a case.

    Synchronous today. The analysis job lifecycle (queue, poll, cancel) is
    tracked separately; this endpoint keeps the same response shape so the
    frontend contract does not change when it moves behind a job.
    """
    try:
        case = get_case(case_id)
    except CaseDefinitionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    settings = get_settings()
    analysis_request = case.to_request(
        data_mode="simulated" if request.synthetic else "observed",
        seed=settings.random_seed,
        min_donors=request.min_donors,
    )

    try:
        data = (
            synthetic_access(analysis_request, true_effect=request.true_effect)
            if request.synthetic
            else earth_engine_access(analysis_request)
        )
    except DataUnavailableError as exc:
        # Observed-data access is refused, never silently served from fixtures.
        raise HTTPException(status_code=501, detail=str(exc)) from exc

    result: AnalysisResult = run_analysis(analysis_request, data)

    if result.status is not EngineStatus.COMPLETED:
        assert result.error is not None  # guaranteed by the contract validator
        raise HTTPException(
            status_code=ERROR_STATUS.get(result.error.code, 500),
            detail={
                "code": result.error.code.value,
                "message": result.error.message,
                "stage": result.error.stage,
                "is_refusal": result.error.is_refusal,
                "remediation": result.error.remediation,
                "run_id": result.run_id,
            },
        )

    bundle = result.bundle
    assert bundle is not None and bundle.verdict is not None
    report = generate_report(bundle) if request.include_report else None

    return VerificationResponse(
        run_id=result.run_id,
        case_id=result.case_id,
        spec_hash=result.spec_hash,
        engine_version=result.engine.engine_version,
        contract_version=result.contract_version,
        data_mode="simulated" if result.is_simulated else "observed",
        duration_ms=result.metrics.duration_ms,
        verdict_label=bundle.verdict.label,
        verdict_rationale=bundle.verdict.rationale,
        caveats=list(bundle.verdict.caveats),
        warnings=list(bundle.warnings),
        bundle=bundle,
        report_markdown=report.markdown if report else None,
        report_generator=report.generator if report else None,
    )
