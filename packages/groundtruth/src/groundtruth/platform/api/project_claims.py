"""Project claim routes: promote a statement, correct it, withdraw it, and see how it matches evidence.

A claim exists only because a person promoted a candidate statement (or typed one). Promotion
re-reads the source document and records exactly what was extracted; later edits never change that
record. Each claim is matched against the evidence on file and reported as supported, partially
supported, contradicted, or insufficiently evidenced, with reasons. No route marks anything
"verified".
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from groundtruth.claims.evidence_match import CHECKABLE_KINDS, KIND_LABELS, ClaimOutcome, kind_note
from groundtruth.platform.api.errors import ApiErrorBody
from groundtruth.platform.api.scope import audit
from groundtruth.platform.auth.authz import Action, Capability, ProjectAccess, require_project
from groundtruth.platform.auth.deps import resolve_sessions
from groundtruth.platform.auth.service import auth_error
from groundtruth.platform.config import get_settings
from groundtruth.platform.projects import claims_service as svc
from groundtruth.platform.store.models import ProjectRow

router = APIRouter(tags=["project-claims"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ApiErrorBody, "description": "Not signed in."},
    403: {"model": ApiErrorBody, "description": "Your access level or role does not allow this."},
    404: {"model": ApiErrorBody, "description": "Unknown project or claim."},
    409: {"model": ApiErrorBody, "description": "Conflicts with the current state."},
    422: {"model": ApiErrorBody, "description": "The claim cannot be accepted."},
}

Viewer = Annotated[ProjectAccess, Depends(require_project(Capability.OVERVIEW))]
Editor = Annotated[
    ProjectAccess, Depends(require_project(Capability.EDIT, action=Action.EDIT_PROJECT))
]

Outcome = Literal["SUPPORTED", "PARTIALLY_SUPPORTED", "CONTRADICTED", "UNVERIFIED"]

NOTE = (
    "A claim is what someone said, not a finding. Each one is compared with the evidence on file. "
    "UNVERIFIED means the evidence needed to test it is missing or of a kind that cannot establish "
    "it; it does not mean the claim is false."
)


class ClaimCreate(BaseModel):
    """Promote a statement from a document (document_id + start + end) or type one (statement_text)."""

    document_id: str | None = Field(default=None, description="The source document.")
    start: int | None = Field(
        default=None, description="Start of the statement in the document text."
    )
    end: int | None = Field(default=None, description="End of the statement in the document text.")
    statement_text: str | None = Field(
        default=None, description="Corrected or typed claim wording."
    )
    kind: str | None = Field(default=None, description="Claim type; defaults to the extracted one.")
    value: float | None = None
    unit: str | None = None
    period: str | None = None


class ClaimPatch(BaseModel):
    """Corrections. Only the fields sent change; the original extraction is never altered."""

    statement_text: str | None = None
    kind: str | None = None
    value: float | None = None
    unit: str | None = None
    period: str | None = None


class ClaimSourceView(BaseModel):
    project_claim_id: str
    document_id: str | None
    document_name: str | None
    document_sha256: str | None
    start: int | None
    end: int | None
    original_text: str = Field(description="Exactly what the document said. Never edited.")
    original_kind: str | None
    original_value: float | None
    original_unit: str | None
    original_period: str | None
    statement_text: str
    kind: str
    value: float | None
    unit: str | None
    period: str | None
    edited: bool = Field(description="True when the tested claim differs from what was extracted.")
    created_at: str | None
    updated_at: str | None


class ClaimOutcomeView(BaseModel):
    status: Outcome
    headline: str
    reasons: list[str]
    supporting: list[str]
    contradicting: list[str]
    required_evidence: list[str]
    available_evidence: list[str]
    missing_evidence: list[str]
    limitations: list[str]
    observed_value: float | None
    observed_unit: str | None
    discrepancy_percentage: float | None
    methodology: str


class ClaimView(BaseModel):
    id: str
    kind_label: str
    checkable: bool = Field(
        description="Whether the platform has any check for this kind of claim."
    )
    source: ClaimSourceView
    outcome: ClaimOutcomeView


class KindView(BaseModel):
    kind: str
    label: str
    checkable: bool
    note: str


class ClaimListView(BaseModel):
    project_id: str
    claims: list[ClaimView]
    kinds: list[KindView]
    note: str = NOTE


def _outcome(o: ClaimOutcome) -> ClaimOutcomeView:
    return ClaimOutcomeView(
        status=o.status,  # type: ignore[arg-type]
        headline=o.headline,
        reasons=o.reasons,
        supporting=o.supporting,
        contradicting=o.contradicting,
        required_evidence=o.required_evidence,
        available_evidence=o.available_evidence,
        missing_evidence=o.missing_evidence,
        limitations=o.limitations,
        observed_value=o.observed_value,
        observed_unit=o.observed_unit,
        discrepancy_percentage=o.discrepancy_percentage,
        methodology=o.methodology,
    )


def _view(row: Any, outcome: ClaimOutcome) -> ClaimView:
    return ClaimView(
        id=row.id,
        kind_label=KIND_LABELS.get(row.kind, row.kind),
        checkable=row.kind in CHECKABLE_KINDS,
        source=ClaimSourceView(**svc.source_view(row)),
        outcome=_outcome(outcome),
    )


def _kinds() -> list[KindView]:
    return [
        KindView(
            kind=k, label=KIND_LABELS.get(k, k), checkable=k in CHECKABLE_KINDS, note=kind_note(k)
        )
        for k in svc.ALLOWED_KINDS
    ]


def _reject(exc: svc.ClaimInputError) -> HTTPException:
    return HTTPException(
        status_code=exc.status,
        detail={"code": exc.code, "message": exc.message, "hint": exc.hint},
    )


def _evaluate_one(db: Any, project_id: str, row: Any) -> ClaimView:
    project = db.get(ProjectRow, project_id)
    if project is None:
        raise auth_error("not_found", "Project not found.")
    ((r, outcome),) = svc.evaluate(project, [row], get_settings().data_dir)
    return _view(r, outcome)


@router.get(
    "/projects/{project_id}/claims",
    response_model=ClaimListView,
    summary="Claims promoted for this project, each matched against the evidence on file",
    responses=_ERRORS,
)
def list_claims(request: Request, access: Viewer) -> ClaimListView:
    with resolve_sessions(request)() as db:
        project = db.get(ProjectRow, access.project.id)
        if project is None:
            raise auth_error("not_found", "Project not found.")
        rows = svc.list_claims(db, access.project.id)
        pairs = svc.evaluate(project, rows, get_settings().data_dir)
        views = [_view(r, o) for r, o in pairs]
    return ClaimListView(project_id=access.project.id, claims=views, kinds=_kinds())


@router.post(
    "/projects/{project_id}/claims",
    response_model=ClaimView,
    status_code=201,
    summary="Promote a statement from a document, or add a claim, for verification",
    responses=_ERRORS,
)
def create_claim(body: ClaimCreate, request: Request, access: Editor) -> ClaimView:
    payload = {
        "document_id": body.document_id,
        "start": body.start,
        "end": body.end,
        "statement_text": body.statement_text,
        "kind": body.kind,
        "value": body.value,
        "unit": body.unit,
        "period": body.period,
    }
    with resolve_sessions(request)() as db:
        project = db.get(ProjectRow, access.project.id)
        if project is None:
            raise auth_error("not_found", "Project not found.")
        try:
            row = svc.create_claim(db, project, access.ctx.user_id, payload)
        except svc.ClaimInputError as exc:
            raise _reject(exc) from exc
        db.commit()
        view = _evaluate_one(db, access.project.id, row)
    audit(
        request,
        access.ctx,
        action="claim.promote",
        resource_type="project_claim",
        resource_id=view.id,
        details={
            "project_id": access.project.id,
            "document_id": view.source.document_id,
            "kind": view.source.kind,
            "edited": view.source.edited,
        },
    )
    return view


@router.patch(
    "/projects/{project_id}/claims/{claim_id}",
    response_model=ClaimView,
    summary="Correct a claim's wording, type, value, unit or period",
    responses=_ERRORS,
)
def edit_claim(claim_id: str, body: ClaimPatch, request: Request, access: Editor) -> ClaimView:
    patch = body.model_dump(exclude_unset=True)
    with resolve_sessions(request)() as db:
        row = svc.get_claim(db, access.project.id, claim_id)
        if row is None:
            raise auth_error("not_found", "Claim not found.")
        try:
            svc.update_claim(db, row, access.ctx.user_id, patch)
        except svc.ClaimInputError as exc:
            raise _reject(exc) from exc
        db.commit()
        view = _evaluate_one(db, access.project.id, row)
    audit(
        request,
        access.ctx,
        action="claim.edit",
        resource_type="project_claim",
        resource_id=claim_id,
        details={"project_id": access.project.id, "fields": sorted(patch)},
    )
    return view


@router.delete(
    "/projects/{project_id}/claims/{claim_id}",
    status_code=204,
    summary="Withdraw a claim (the record and its history remain)",
    responses=_ERRORS,
)
def withdraw_claim(claim_id: str, request: Request, access: Editor) -> Response:
    with resolve_sessions(request)() as db:
        row = svc.get_claim(db, access.project.id, claim_id)
        if row is None or row.withdrawn_at is not None:
            raise auth_error("not_found", "Claim not found.")
        svc.withdraw_claim(row, access.ctx.user_id)
        db.commit()
    audit(
        request,
        access.ctx,
        action="claim.withdraw",
        resource_type="project_claim",
        resource_id=claim_id,
        details={"project_id": access.project.id},
    )
    return Response(status_code=204)
