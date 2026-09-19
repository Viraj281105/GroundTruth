"""FastAPI application exposing the verification pipeline."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from groundtruth import __version__
from groundtruth.api.schemas import (
    CaseDetail,
    CaseSummary,
    HealthResponse,
    VerificationRequest,
    VerificationResponse,
)
from groundtruth.cases.registry import get_case, load_all_cases
from groundtruth.config import get_settings
from groundtruth.core.errors import (
    CaseDefinitionError,
    DonorPoolError,
    GroundTruthError,
    InsufficientDataError,
)
from groundtruth.ingestion.synthetic import (
    SyntheticCovariateProvider,
    SyntheticDonorPoolProvider,
    SyntheticObservationProvider,
)
from groundtruth.pipeline import PipelineConfig, run_verification

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
    return HealthResponse(
        version=__version__,
        earth_observation_implemented=False,
        genai_narration_implemented=False,
        cases_available=len(load_all_cases()),
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

    Only simulated runs are available. A request with ``synthetic=false`` is
    rejected with 501 rather than served from simulated data under a real label.
    """
    try:
        case = get_case(case_id)
    except CaseDefinitionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if not request.synthetic:
        raise HTTPException(
            status_code=501,
            detail=(
                "Observed-data verification is not implemented: the Earth Engine reducer chain "
                "has not landed. Set synthetic=true to exercise the pipeline on simulated data."
            ),
        )

    settings = get_settings()
    observation = SyntheticObservationProvider(
        seed=settings.random_seed,
        treated_unit_id=case.case_id,
        true_effect=request.true_effect,
        treatment_period=case.window.post_start,
    )

    try:
        result = run_verification(
            case,
            observation,
            SyntheticCovariateProvider(seed=settings.random_seed, project_unit_id=case.case_id),
            SyntheticDonorPoolProvider(),
            config=PipelineConfig(min_donors=request.min_donors),
        )
    except (InsufficientDataError, DonorPoolError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except GroundTruthError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    verdict = result.bundle.verdict
    assert verdict is not None  # the assembler always attaches one
    return VerificationResponse(
        case_id=case.case_id,
        data_mode="simulated",
        verdict_label=verdict.label.value,
        verdict_rationale=verdict.rationale,
        caveats=list(verdict.caveats),
        warnings=list(result.bundle.warnings),
        bundle=result.bundle,
        report_markdown=result.report.markdown if request.include_report else None,
        report_generator=result.report.generator if request.include_report else None,
    )
