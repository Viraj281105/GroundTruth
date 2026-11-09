"""GroundTruth 2.0 API Endpoints.

Provides REST endpoints for:
1. Evidence Registry & Source Lifecycles
2. Claim-Level Verification Engine (8 structured claim dimensions)
3. Groq LPU Environmental Intelligence & Due Diligence
4. Independent Validation Benchmark Suite
5. Cryptographic Audit Ledger & Reproducibility
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from groundtruth.claims.verification_engine import (
    verify_project_claims,
)
from groundtruth.engine.benchmark.suite import run_independent_benchmark_suite
from groundtruth.platform.api.rate_limiting import RateLimiter
from groundtruth.platform.audit.ledger import get_global_audit_ledger
from groundtruth.platform.datasets.evidence_registry import (
    SourceLifecycle,
    get_global_evidence_registry,
)
from groundtruth.platform.intelligence.groq_service import (
    IntelligenceMode,
    get_global_intelligence_service,
)

router = APIRouter(tags=["v2-intelligence-evidence"])


# ---------------------------------------------------------------------------
# 1. Evidence Registry
# ---------------------------------------------------------------------------


class EvidenceSourceResponse(BaseModel):
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
    acquisition_date: str
    retrieval_timestamp: str
    processing_history: list[dict[str, Any]]
    data_quality_score: float
    completeness_percentage: float
    missingness_summary: str
    content_hash: str
    lifecycle: str
    is_operational_integration: bool
    sutva_compliant: bool
    quarantine_reason: str | None = None
    notes: str = ""


class EvidenceRegistryResponse(BaseModel):
    total_registered: int
    discovered: int
    accessible: int
    integrated: int
    validated: int
    quarantined: int
    operational_count: int
    average_completeness: float
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
        average_completeness=stats["average_completeness"],
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
    project_id: str = Field(default="kariba-redd", description="Unique project slug or ID")
    custom_claims: list[dict[str, Any]] | None = Field(
        default=None, description="Optional custom claim list"
    )


@router.get("/claims/structured/{project_id}", summary="Get structured claim verifications")
@router.get(
    "/api/v1/claims/structured/{project_id}", summary="Get structured claim verifications (v1)"
)
def get_structured_claims(project_id: str) -> dict[str, Any]:
    portfolio = verify_project_claims(project_id=project_id)
    return portfolio.to_dict()


@router.post("/claims/verify-structured", summary="Run claim-level verification")
@router.post("/api/v1/claims/verify-structured", summary="Run claim-level verification (v1)")
def verify_claims_structured(req: ClaimVerificationRequest) -> dict[str, Any]:
    portfolio = verify_project_claims(project_id=req.project_id, custom_claims=req.custom_claims)
    return portfolio.to_dict()


# ---------------------------------------------------------------------------
# 3. Groq Intelligence Integration
# ---------------------------------------------------------------------------


class IntelligenceQueryRequest(BaseModel):
    query: str = Field(min_length=3, max_length=1000, description="Intelligence inquiry topic")
    mode: IntelligenceMode = Field(
        default=IntelligenceMode.CSR_DUE_DILIGENCE, description="Research mode"
    )
    project_id: str = Field(default="kariba-redd", description="Target project identifier")
    stakeholder_role: str | None = Field(
        default="csr", description="Stakeholder lens: csr | auditor | ngo"
    )


@router.post(
    "/intelligence/research",
    summary="Run Groq environmental intelligence inquiry",
    dependencies=[Depends(RateLimiter(limit=10, window_seconds=60, scope_prefix="intelligence"))],
)
@router.post(
    "/api/v1/intelligence/research",
    summary="Run Groq environmental intelligence inquiry (v1)",
    dependencies=[Depends(RateLimiter(limit=10, window_seconds=60, scope_prefix="intelligence"))],
)
def research_intelligence(req: IntelligenceQueryRequest) -> dict[str, Any]:
    service = get_global_intelligence_service()
    res = service.execute_intelligence_query(
        query=req.query,
        mode=req.mode,
        project_id=req.project_id,
        stakeholder_role=req.stakeholder_role,
    )
    return res.to_dict()


# ---------------------------------------------------------------------------
# 4. Independent Validation Benchmark Suite
# ---------------------------------------------------------------------------


@router.get("/benchmarks", summary="Run and return independent validation benchmark suite")
@router.get(
    "/api/v1/benchmarks", summary="Run and return independent validation benchmark suite (v1)"
)
def get_benchmarks() -> dict[str, Any]:
    summary = run_independent_benchmark_suite()
    return summary.to_dict()


# ---------------------------------------------------------------------------
# 5. Cryptographic Audit Ledger & Reproducibility
# ---------------------------------------------------------------------------


class ReproducibilityCheckRequest(BaseModel):
    record_id: str
    recomputed_findings: dict[str, Any]


@router.get("/audit/ledger/{project_id}", summary="Get audit ledger records for project")
@router.get(
    "/api/v1/audit/ledger/{project_id}", summary="Get audit ledger records for project (v1)"
)
def get_audit_records(project_id: str) -> list[dict[str, Any]]:
    ledger = get_global_audit_ledger()
    records = ledger.get_records(project_id)
    return [r.to_dict() for r in records]


@router.post("/audit/verify-reproducibility", summary="Verify deterministic result reproduction")
@router.post(
    "/api/v1/audit/verify-reproducibility", summary="Verify deterministic result reproduction (v1)"
)
def verify_reproducibility(req: ReproducibilityCheckRequest) -> dict[str, Any]:
    ledger = get_global_audit_ledger()
    passed = ledger.verify_reproducibility(req.record_id, req.recomputed_findings)
    return {
        "record_id": req.record_id,
        "reproducibility_verified": passed,
        "message": (
            "Deterministic findings reproduced bit-for-bit."
            if passed
            else "Findings diverged from recorded cryptographic audit hash."
        ),
    }
