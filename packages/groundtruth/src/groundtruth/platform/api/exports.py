"""FastAPI export endpoints for institutional CSV and PDF verification reports."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Response

from groundtruth.contracts.errors import CaseDefinitionError
from groundtruth.contracts.evidence import EvidenceBundle
from groundtruth.engine.run import run_analysis
from groundtruth.platform.cases.registry import get_case
from groundtruth.platform.datasets.access import synthetic_access
from groundtruth.platform.reports.exporters import export_bundle_csv, export_bundle_pdf
from groundtruth.platform.reports.narrative import generate_report

router = APIRouter(prefix="/cases", tags=["exports"])


def build_case_bundle(
    case_id: str,
    *,
    seed: int = 20260101,
    true_effect: float = 0.06,
) -> EvidenceBundle:
    """Run a deterministic synthetic screening analysis for ``case_id`` and return its bundle."""
    try:
        case = get_case(case_id)
    except (KeyError, CaseDefinitionError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=f"Case {case_id!r} not found") from exc

    req = case.to_request(seed=seed)
    access = synthetic_access(req, true_effect=true_effect)
    result = run_analysis(req, access)
    if result.bundle is None:
        raise HTTPException(
            status_code=500,
            detail=f"Screening analysis for {case_id!r} failed to produce an evidence bundle.",
        )
    return result.bundle


@router.get("/{case_id}/export/csv")
def export_case_csv(
    case_id: str,
    seed: int = Query(default=20260101, description="Deterministic RNG seed"),
) -> Response:
    """Export the case's evidence bundle as a UTF-8 CSV attachment."""
    bundle = build_case_bundle(case_id, seed=seed)
    csv_text = export_bundle_csv(bundle)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{case_id}-evidence.csv"',
            "X-GroundTruth-Data-Mode": "simulated",
        },
    )


@router.get("/{case_id}/export/pdf")
def export_case_pdf(
    case_id: str,
    seed: int = Query(default=20260101, description="Deterministic RNG seed"),
) -> Response:
    """Export the case's screening verification report as a self-contained PDF attachment."""
    bundle = build_case_bundle(case_id, seed=seed)
    report = generate_report(bundle)
    pdf_bytes = export_bundle_pdf(bundle, report_markdown=report.markdown)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{case_id}-report.pdf"',
            "X-GroundTruth-Data-Mode": "simulated",
        },
    )
