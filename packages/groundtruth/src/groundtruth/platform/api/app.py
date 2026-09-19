"""FastAPI application exposing the verification pipeline.

**Owner: Bhumi.**

This module talks to the engine through exactly three names — ``run_analysis``,
``describe_engine`` and ``ENGINE_VERSION`` — and otherwise knows nothing about
how an analysis is computed. Swapping the estimator, the solver or the whole
engine internals requires no change here.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from groundtruth import __version__
from groundtruth.contracts import CONTRACT_VERSION
from groundtruth.contracts.errors import CaseDefinitionError, DataUnavailableError
from groundtruth.contracts.result import AnalysisResult, EngineStatus, ErrorCode
from groundtruth.engine import ENGINE_VERSION, describe_engine, run_analysis
from groundtruth.platform.api.schemas import (
    CaseDetail,
    CaseSummary,
    HealthResponse,
    VerificationRequest,
    VerificationResponse,
)
from groundtruth.platform.cases.registry import get_case, load_all_cases
from groundtruth.platform.config import get_settings
from groundtruth.platform.datasets.access import earth_engine_access, synthetic_access
from groundtruth.platform.reports.narrative import generate_report

app = FastAPI(
    title="GroundTruth",
    version=__version__,
    description=(
        "Independent causal verification for climate restoration and carbon-credit claims. "
        "This API returns evidence bundles with full provenance, not bare scores. A divergence "
        "between an independent estimate and a developer claim is a trigger for accredited "
        "review, never a finding of fraud."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_settings().frontend_url],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

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


@app.get("/cases/{case_id}", response_model=CaseDetail, tags=["cases"])
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


@app.post("/cases/{case_id}/verify", response_model=VerificationResponse, tags=["verification"])
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
        verdict_label=bundle.verdict.label.value,
        verdict_rationale=bundle.verdict.rationale,
        caveats=list(bundle.verdict.caveats),
        warnings=list(bundle.warnings),
        bundle=bundle,
        report_markdown=report.markdown if report else None,
        report_generator=report.generator if report else None,
    )
