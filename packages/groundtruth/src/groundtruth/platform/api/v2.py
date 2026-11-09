"""GroundTruth 2.0 API Endpoints.

Provides REST endpoints for:
1. Evidence Registry & Source Lifecycles
2. Claim-Level Verification Engine (8 structured claim dimensions)
3. Groq LPU Environmental Intelligence & Due Diligence
4. Independent Validation Benchmark Suite
5. Cryptographic Audit Ledger & Reproducibility
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from groundtruth.claims.verification_engine import (
    verify_project_claims,
)
from groundtruth.engine.benchmark.suite import run_independent_benchmark_suite
from groundtruth.platform.api.rate_limiting import RateLimiter
from groundtruth.platform.auth.authz import (
    AccessContext,
    Capability,
    Context,
    ProjectAccess,
    authorize_project,
    get_access_context,
    require_project,
)
from groundtruth.platform.auth.deps import resolve_sessions
from groundtruth.platform.config import get_settings
from groundtruth.platform.datasets.evidence_registry import (
    SourceLifecycle,
    get_global_evidence_registry,
)
from groundtruth.platform.intelligence.groq_service import (
    IntelligenceMode,
    get_global_intelligence_service,
)
from groundtruth.platform.projects.claim_gaps import claim_gaps
from groundtruth.platform.store.models import ProjectRow

router = APIRouter(tags=["v2-intelligence-evidence"])


# ---------------------------------------------------------------------------
# 1. Evidence Registry
# ---------------------------------------------------------------------------


class EvidenceSourceResponse(BaseModel):
    """Truthful classification of one dataset. Public reference metadata only (no tenant data)."""

    source_id: str
    title: str
    provider: str
    source_url: str
    dataset_identifier: str
    version: str
    license: str
    permitted_usage: str
    modality: str
    spatial_coverage: str
    temporal_coverage_start: str
    temporal_coverage_end: str
    spatial_resolution: str
    temporal_resolution: str
    acquisition_date: str | None = None
    retrieval_timestamp: str | None = Field(
        default=None, description="Null when the dataset was never retrieved."
    )
    processing_history: list[dict[str, Any]]
    data_quality_score: float | None = Field(
        default=None, description="Null unless measured from retrieved data."
    )
    completeness_percentage: float | None = Field(
        default=None, description="Null unless measured from retrieved data."
    )
    missingness_summary: str
    content_hash: str | None = Field(
        default=None, description="sha256 of a real local artefact; null otherwise."
    )
    lifecycle: str
    is_operational_integration: bool = Field(
        description="True only with a validated automated ingestion path."
    )
    sutva_compliant: bool
    quarantine_reason: str | None = None
    notes: str = ""
    ingestion_mode: str = Field(
        description="automated_operational | manual_staging | curated_vector | "
        "accessible_unvalidated | scaffolded | quarantined | synthetic_simulated"
    )
    validation_status: str = Field(description="validated | unvalidated | failed | not_applicable")
    validation_evidence: str = "none"
    blocked_for_production_analysis: bool = True
    blocked_reason: str | None = None
    quality_measured: bool = False
    quality_note: str = ""
    retrieval_status: str = "not_retrieved"
    retrieval_provenance: str | None = None
    content_hash_scope: str | None = None
    retrieved_temporal_coverage: str | None = None
    local_artifact_paths: list[str] = Field(default_factory=list)
    artifacts_present: bool | None = None


class EvidenceRegistryResponse(BaseModel):
    total_registered: int
    discovered: int
    accessible: int
    integrated: int
    validated: int
    quarantined: int
    operational_count: int
    usable_for_production_count: int = 0
    blocked_count: int = 0
    synthetic_count: int = 0
    ingestion_mode_counts: dict[str, int] = Field(default_factory=dict)
    average_completeness: float | None = Field(
        default=None, description="Mean over sources with measured completeness; null if none."
    )
    completeness_measured_count: int = 0
    sources: list[EvidenceSourceResponse]


@router.get(
    "/evidence-registry", response_model=EvidenceRegistryResponse, summary="List evidence sources"
)
@router.get(
    "/api/v1/evidence-registry",
    response_model=EvidenceRegistryResponse,
    summary="List evidence sources (v1)",
)
def list_evidence_sources(
    lifecycle: SourceLifecycle | None = Query(
        default=None, description="Filter by lifecycle state"
    ),
    operational_only: bool = Query(
        default=False, description="Filter to operational integrations only"
    ),
) -> EvidenceRegistryResponse:
    # Public reference metadata only: no tenant/project/user data is held in the registry,
    # so these endpoints are intentionally unauthenticated (documented, tested).
    registry = get_global_evidence_registry()
    sources = registry.list_sources(lifecycle=lifecycle, operational_only=operational_only)
    stats = registry.get_summary_statistics()
    return EvidenceRegistryResponse(
        total_registered=stats["total_registered"],
        discovered=stats["discovered"],
        accessible=stats["accessible"],
        integrated=stats["integrated"],
        validated=stats["validated"],
        quarantined=stats["quarantined"],
        operational_count=stats["operational_count"],
        usable_for_production_count=stats["usable_for_production_count"],
        blocked_count=stats["blocked_count"],
        synthetic_count=stats["synthetic_count"],
        ingestion_mode_counts=stats["ingestion_mode_counts"],
        average_completeness=stats["average_completeness"],
        completeness_measured_count=stats["completeness_measured_count"],
        sources=[EvidenceSourceResponse(**s.to_dict()) for s in sources],
    )


@router.get(
    "/evidence-registry/{source_id}",
    response_model=EvidenceSourceResponse,
    summary="Get single evidence source",
)
@router.get(
    "/api/v1/evidence-registry/{source_id}",
    response_model=EvidenceSourceResponse,
    summary="Get single evidence source (v1)",
)
def get_evidence_source(source_id: str) -> EvidenceSourceResponse:
    registry = get_global_evidence_registry()
    source = registry.get_source(source_id)
    if not source:
        raise HTTPException(status_code=404, detail=f"Evidence source '{source_id}' not found.")
    return EvidenceSourceResponse(**source.to_dict())


# ---------------------------------------------------------------------------
# 2. Claim-Level Verification Engine
# ---------------------------------------------------------------------------


class ClaimVerificationRequest(BaseModel):
    project_id: str = Field(default="kariba-redd", description="Project UUID or slug")
    custom_claims: list[dict[str, Any]] | None = Field(
        default=None, description="Optional custom claim list"
    )


KARIBA_CASE_ID = "kariba-redd"
"""The only project whose claims may be the demonstration suite (the seeded Kariba case)."""

ClaimsReader = Annotated[ProjectAccess, Depends(require_project(Capability.OVERVIEW))]


def _portfolio_for(
    project: ProjectRow, custom_claims: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Project-scoped portfolio. Kariba demo data only for the seeded Kariba project."""
    is_kariba = project.case_id == KARIBA_CASE_ID and not custom_claims
    mode = "synthetic" if project.data_mode == "simulated" else "observed"
    missing: list[dict[str, Any]] = []
    steps: list[str] = []
    if not is_kariba and not custom_claims:
        missing, steps = claim_gaps(project, get_settings().data_dir)
    try:
        portfolio = verify_project_claims(
            project_id=project.id,
            custom_claims=custom_claims,
            project_name=project.name,
            demo_kariba=is_kariba,
            data_mode=mode,
            missing_information=missing,
            next_steps=steps,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return portfolio.to_dict()


@router.get("/claims/structured/{project_id}", summary="Get structured claim verifications")
@router.get(
    "/api/v1/claims/structured/{project_id}", summary="Get structured claim verifications (v1)"
)
def get_structured_claims(access: ClaimsReader) -> dict[str, Any]:
    return _portfolio_for(access.project)


@router.post("/claims/verify-structured", summary="Run claim-level verification")
@router.post("/api/v1/claims/verify-structured", summary="Run claim-level verification (v1)")
def verify_claims_structured(
    req: ClaimVerificationRequest, request: Request, ctx: Context
) -> dict[str, Any]:
    def lookup(db: Session) -> ProjectRow | None:
        return db.execute(
            select(ProjectRow).where(
                (ProjectRow.id == req.project_id) | (ProjectRow.slug == req.project_id)
            )
        ).scalar_one_or_none()

    access = authorize_project(request, ctx, lookup, Capability.OVERVIEW)
    return _portfolio_for(access.project, req.custom_claims)


# ---------------------------------------------------------------------------
# 3. Groq Intelligence Integration
# ---------------------------------------------------------------------------


class IntelligenceQueryRequest(BaseModel):
    query: str = Field(min_length=3, max_length=1000, description="Intelligence inquiry topic")
    mode: IntelligenceMode = Field(
        default=IntelligenceMode.CSR_DUE_DILIGENCE, description="Research mode"
    )
    project_id: str = Field(min_length=1, max_length=64, description="Project id (UUID)")
    stakeholder_role: str | None = Field(
        default=None, description="Optional stakeholder lens: csr | auditor | ngo"
    )


def _intelligence_project(request: Request, ctx: AccessContext, project_ref: str) -> ProjectAccess:
    """Authorize the body's ``project_id`` through the one project authorization path."""
    from sqlalchemy import select

    from groundtruth.platform.store.models import ProjectRow

    def lookup(db: Any) -> Any:
        return db.execute(
            select(ProjectRow).where(
                (ProjectRow.id == project_ref) | (ProjectRow.slug == project_ref)
            )
        ).scalar_one_or_none()

    return authorize_project(request, ctx, lookup, Capability.OVERVIEW)


@router.get(
    "/intelligence/status",
    summary="Whether the Groq intelligence provider is configured (no secrets)",
    dependencies=[Depends(get_access_context)],
)
@router.get(
    "/api/v1/intelligence/status",
    summary="Whether the Groq intelligence provider is configured (v1)",
    dependencies=[Depends(get_access_context)],
)
def intelligence_status() -> dict[str, Any]:
    return get_global_intelligence_service().status()


@router.post(
    "/intelligence/research",
    summary="Project-scoped intelligence inquiry over the project's own retrieved records",
    dependencies=[Depends(RateLimiter(limit=10, window_seconds=60, scope_prefix="intelligence"))],
)
@router.post(
    "/api/v1/intelligence/research",
    summary="Project-scoped intelligence inquiry (v1)",
    dependencies=[Depends(RateLimiter(limit=10, window_seconds=60, scope_prefix="intelligence"))],
)
def research_intelligence(
    req: IntelligenceQueryRequest, request: Request, ctx: Context
) -> dict[str, Any]:
    from groundtruth.platform.config import get_settings
    from groundtruth.platform.intelligence.context import build_project_context
    from groundtruth.platform.projects import documents as project_documents
    from groundtruth.platform.projects import service as project_service

    access = _intelligence_project(request, ctx, req.project_id)
    with resolve_sessions(request)() as db:
        project = project_service.get_project(db, access.project.id)
        if project is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "not_found", "message": "Project not found.", "hint": None},
            )
        # Real uploaded documents (filename/status only: contents never reach the model).
        documents = [
            project_documents.document_dict(d)
            for d in project_documents.list_documents(db, access.project.id)
        ]
        db.expunge(project)
    context = build_project_context(
        project, access.level, get_settings().data_dir, documents=documents
    )
    return get_global_intelligence_service().execute_intelligence_query(
        query=req.query,
        context=context,
        mode=req.mode,
        stakeholder_role=req.stakeholder_role,
    )


# ---------------------------------------------------------------------------
# 4. Independent Validation Benchmark Suite
# ---------------------------------------------------------------------------


@router.get("/benchmarks", summary="Run and return independent validation benchmark suite")
@router.get(
    "/api/v1/benchmarks", summary="Run and return independent validation benchmark suite (v1)"
)
def get_benchmarks(ctx: Context) -> dict[str, Any]:
    """Runs a compute suite, so it needs a signed-in user (it was previously open to anyone)."""
    summary = run_independent_benchmark_suite()
    return summary.to_dict()


# ---------------------------------------------------------------------------
# 5. Audit ledger
# ---------------------------------------------------------------------------
# The ledger routes live in ``platform/api/ledger.py`` and are scoped to the caller's own
# projects. The former global, unauthenticated ``/audit/ledger/{project_id}`` routes served an
# invented Kariba record for any id and were removed.
