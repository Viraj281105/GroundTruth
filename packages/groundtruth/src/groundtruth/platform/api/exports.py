"""FastAPI export endpoints for institutional CSV and PDF verification reports.

Both need the monitoring-report export capability on the case's project, which every grant
level has, so a funder with a ``view`` grant may export. Each successful export is audited
(``export.download``) against the project.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from groundtruth.contracts.errors import CaseDefinitionError, ConfigurationError
from groundtruth.contracts.evidence import EvidenceBundle
from groundtruth.engine import run_analysis
from groundtruth.platform.api.errors import ApiErrorCode, api_error
from groundtruth.platform.api.scope import audit, case_dependency
from groundtruth.platform.auth.authz import Capability, ProjectAccess
from groundtruth.platform.cases.registry import get_case
from groundtruth.platform.config import get_settings
from groundtruth.platform.datasets.access import synthetic_access
from groundtruth.platform.reports.export_pipeline import (
    NarrationFailedError,
    NarrationNotGroundedError,
    ReportExportError,
    build_export_report,
)
from groundtruth.platform.reports.exporters import (
    bundle_is_simulated,
    export_bundle_csv,
    export_bundle_pdf,
)
from groundtruth.platform.reports.providers import build_narrator

REPORT_GENERATOR_HEADER = "X-GroundTruth-Report-Generator"

router = APIRouter(prefix="/cases", tags=["exports"])

Exporter = Annotated[ProjectAccess, Depends(case_dependency(Capability.REPORT_EXPORT))]


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


def _data_mode(bundle: EvidenceBundle) -> str:
    """What the bundle actually is, not a constant: an export must not mislabel its data."""
    return "simulated" if bundle_is_simulated(bundle) else "observed"


def _narrator(narrate: bool) -> object | None:
    """The configured narrator when one was asked for, or a structured 422."""
    if not narrate:
        return None
    try:
        narrator = build_narrator(get_settings())
    except ConfigurationError as exc:
        raise api_error(
            ApiErrorCode.NARRATION_NOT_CONFIGURED,
            str(exc),
            hint="Set the provider's API key, or omit narrate to export the deterministic report.",
        ) from exc
    if narrator is None:
        raise api_error(
            ApiErrorCode.NARRATION_NOT_CONFIGURED,
            "narrate=true was asked for, but no GenAI provider is configured (GENAI_PROVIDER=none).",
            hint="Set GENAI_PROVIDER and its API key, or omit narrate for the deterministic report.",
        )
    return narrator


def _report_hint(code: ApiErrorCode) -> str:
    if code is ApiErrorCode.REPORT_NOT_GROUNDED:
        return "This is a defect, not something to retry around. Report it with the request id."
    return "Export without narrate for the deterministic report, or try again."


_REPORT_ERRORS = {
    NarrationFailedError: ApiErrorCode.NARRATION_FAILED,
    NarrationNotGroundedError: ApiErrorCode.NARRATION_NOT_GROUNDED,
}


@router.get("/{case_id}/export/csv")
def export_case_csv(
    case_id: str,
    request: Request,
    access: Exporter,
    seed: int = Query(default=20260101, description="Deterministic RNG seed"),
) -> Response:
    """Export the case's evidence bundle as a UTF-8 CSV attachment."""
    bundle = build_case_bundle(case_id, seed=seed)
    csv_text = export_bundle_csv(bundle)
    audit(
        request,
        access.ctx,
        action="export.download",
        resource_type="project",
        resource_id=access.project.id,
        details={"format": "csv", "case_id": case_id},
    )
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{case_id}-evidence.csv"',
            "X-GroundTruth-Data-Mode": _data_mode(bundle),
            REPORT_GENERATOR_HEADER: "deterministic",
        },
    )


@router.get("/{case_id}/export/pdf")
def export_case_pdf(
    case_id: str,
    request: Request,
    access: Exporter,
    seed: int = Query(default=20260101, description="Deterministic RNG seed"),
    narrate: bool = Query(
        default=False,
        description=(
            "Narrate the report with the configured GenAI provider. The narration is verified "
            "against the bundle first, and the export is refused (never substituted) if it fails."
        ),
    ),
) -> Response:
    """Export the case's screening verification report as a self-contained PDF attachment.

    The report is verified against its own evidence bundle before it is exported, and the PDF
    says which generator wrote it. Without ``narrate`` it is the deterministic report.
    """
    bundle = build_case_bundle(case_id, seed=seed)
    narrator = _narrator(narrate)
    try:
        report = build_export_report(bundle, narrator=narrator)
    except ReportExportError as exc:
        code = next(
            (c for kind, c in _REPORT_ERRORS.items() if isinstance(exc, kind)),
            ApiErrorCode.REPORT_NOT_GROUNDED,
        )
        raise api_error(code, str(exc), hint=_report_hint(code)) from exc
    pdf_bytes = export_bundle_pdf(
        bundle, report_markdown=report.markdown, generator=report.generator
    )
    audit(
        request,
        access.ctx,
        action="export.download",
        resource_type="project",
        resource_id=access.project.id,
        details={"format": "pdf", "case_id": case_id, "generator": report.generator},
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{case_id}-report.pdf"',
            "X-GroundTruth-Data-Mode": _data_mode(bundle),
            REPORT_GENERATOR_HEADER: report.generator,
        },
    )
