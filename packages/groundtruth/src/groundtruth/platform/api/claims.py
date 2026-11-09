"""Screening aid: extract quantitative claims from document text.

Rule-based extraction only (no language model). Every claim carries the character span it
was read from. When a case is named, a claim is set beside a figure only where the case
actually holds one; otherwise ``estimated`` is ``null`` and the note says so. Wording is
neutral: a difference warrants accredited review and is not a finding about any party.
"""

from __future__ import annotations

import base64
import io
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from groundtruth.claims import Claim, ClaimKind, analyze_text, compare_claims, extract_claims
from groundtruth.contracts.errors import CaseDefinitionError
from groundtruth.platform.api.schemas import MessageErrorBody
from groundtruth.platform.auth.deps import require_role
from groundtruth.platform.cases.registry import get_case

router = APIRouter(tags=["claims"])

MAX_TEXT_CHARS = 200_000

DISCLAIMER_BASE = (
    "Screening aid only. Extracted figures are read from the text by fixed patterns and may be "
    "incomplete or misread. A difference between two figures warrants accredited review; it is "
    "not a finding about any person or organisation."
)
NO_CASE_NOTE = " No case was selected, so no figure was set beside the extracted claims."


class ClaimsRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)
    case_id: str | None = None


class ClaimSpan(BaseModel):
    start: int
    end: int
    text: str


class ExtractedClaim(BaseModel):
    kind: str
    value: float
    unit: str
    span: ClaimSpan


class ClaimComparison(BaseModel):
    claim_kind: str
    claimed: float
    estimated: float | None
    note: str


class ClaimStatementModel(BaseModel):
    """One statement read from the text (additive; see ``claims.statements``)."""

    statement_id: str
    kind: str
    status: str
    """``extracted`` | ``unsupported_by_available_evidence`` | ``overclaim``."""
    text: str
    span: ClaimSpan
    value: float | None = None
    unit: str | None = None
    period: str | None = None
    reason: str
    evidence_link: str | None = None
    evidence_gap: str | None = None


class ClaimsResponse(BaseModel):
    claims: list[ExtractedClaim]
    comparisons: list[ClaimComparison]
    disclaimer: str
    statements: list[ClaimStatementModel] = Field(default_factory=list)
    unrecognised_sentences: list[ClaimSpan] = Field(default_factory=list)


class PdfExtractRequest(BaseModel):
    file_base64: str
    filename: str = "uploaded.pdf"


class PdfExtractResponse(BaseModel):
    text: str
    num_pages: int
    filename: str


@router.post(
    "/claims/extract-pdf",
    response_model=PdfExtractResponse,
    summary="Extract raw text from an uploaded PDF document",
    dependencies=[Depends(require_role("user"))],
)
def extract_pdf(body: PdfExtractRequest) -> PdfExtractResponse:
    """Extract plain text from base64 PDF bytes (PDD or monitoring report)."""
    import pypdf

    try:
        raw_b64 = body.file_base64
        if "," in raw_b64:
            raw_b64 = raw_b64.split(",", 1)[1]
        contents = base64.b64decode(raw_b64)
        reader = pypdf.PdfReader(io.BytesIO(contents))
        extracted = []
        for page in reader.pages:
            t = page.extract_text() or ""
            if t.strip():
                extracted.append(t.strip())
        text = "\n\n".join(extracted)
        fallback = "No selectable text found in the PDF. Scanned pages require OCR."
        return PdfExtractResponse(
            text=text if text else fallback,
            num_pages=len(reader.pages),
            filename=body.filename,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid PDF: {exc}") from exc


def _to_model(claim: Claim) -> ExtractedClaim:
    return ExtractedClaim(
        kind=claim.kind.value,
        value=claim.value,
        unit=claim.unit,
        span=ClaimSpan(start=claim.start, end=claim.end, text=claim.quote),
    )


@router.post(
    "/claims/analyze",
    response_model=ClaimsResponse,
    summary="Extract quantitative claims from text",
    dependencies=[Depends(require_role("user"))],
    responses={404: {"model": MessageErrorBody, "description": "Unknown case."}},
)
def analyze_claims(body: ClaimsRequest) -> ClaimsResponse:
    """Extract claims with spans; set them beside the case's figures when available."""
    if not body.text.strip():
        raise HTTPException(status_code=422, detail="text must not be blank")
    claims = extract_claims(body.text)
    models = [_to_model(c) for c in claims]
    analysis = analyze_text(body.text)
    extra: dict[str, Any] = {
        "statements": [
            ClaimStatementModel(
                statement_id=st.statement_id,
                kind=st.kind.value,
                status=st.status.value,
                text=st.text,
                span=ClaimSpan(start=st.start, end=st.end, text=st.text),
                value=st.value,
                unit=st.unit,
                period=st.period,
                reason=st.reason,
                evidence_link=st.evidence_link,
                evidence_gap=st.evidence_gap,
            )
            for st in analysis.statements
        ],
        "unrecognised_sentences": [
            ClaimSpan(start=u.start, end=u.end, text=u.text) for u in analysis.unrecognised
        ],
    }
    if body.case_id is None:
        return ClaimsResponse(
            claims=models, comparisons=[], disclaimer=DISCLAIMER_BASE + NO_CASE_NOTE, **extra
        )

    try:
        case = get_case(body.case_id)
    except CaseDefinitionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    area = case.claim.project_area_ha
    credits = case.claim.claimed_credits_tco2e
    reference: dict[str, float] = {}
    if area is not None:
        reference["area_ha"] = float(area)
    if credits is not None:
        reference["credits_issued"] = float(credits)

    differing = {d.citation for d in compare_claims(claims, reference)}
    comparisons: list[ClaimComparison] = []
    for claim in claims:
        if claim.kind is ClaimKind.AREA_HECTARES and area is not None:
            verdict = (
                "differs from the registered area; the difference warrants review"
                if claim.citation() in differing
                else "is within 5% of the registered area"
            )
            note = (
                f"The documented area {verdict}. The comparison figure is the project area in "
                "the case definition, not an Earth-observation estimate."
            )
            comparisons.append(
                ClaimComparison(
                    claim_kind=claim.kind.value,
                    claimed=claim.value,
                    estimated=float(area),
                    note=note,
                )
            )
        elif claim.kind is ClaimKind.CREDITS_ISSUED and credits is not None:
            verdict = (
                "differs from the registered credit count; the difference warrants review"
                if claim.citation() in differing
                else "matches the registered credit count"
            )
            note = (
                f"The documented credit volume {verdict}. Registered figure: {credits:,.0f} tCO2e."
            )
            comparisons.append(
                ClaimComparison(
                    claim_kind=claim.kind.value,
                    claimed=claim.value,
                    estimated=float(credits),
                    note=note,
                )
            )
        else:
            comparisons.append(
                ClaimComparison(
                    claim_kind=claim.kind.value,
                    claimed=claim.value,
                    estimated=None,
                    note="No independent estimate is available for this quantity, so nothing "
                    "is compared.",
                )
            )
    return ClaimsResponse(
        claims=models,
        comparisons=comparisons,
        disclaimer=DISCLAIMER_BASE + " Only figures the case actually holds are compared.",
        **extra,
    )
