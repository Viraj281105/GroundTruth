"""Audit-ledger and report routes, all scoped to the caller's own projects.

* ``GET /projects/{project_id}/ledger``: the project's ledger, verified on every read.
* ``POST /projects/{project_id}/ledger/verify-report``: check a file against the record that sealed it.
* ``GET /orgs/{slug}/reports``: the reports an organization can actually download, built from its
  own projects (owned or granted) and their real ledger state. Nothing is listed unless it exists.

The status shown to users is always the result of :meth:`AuditLedger.verify_project`; it is never
a stored flag.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from groundtruth.platform.api.errors import ApiErrorBody
from groundtruth.platform.api.scope import audit
from groundtruth.platform.audit.ledger import (
    KIND_REPORT_SEALED,
    AuditLedger,
    AuditRecord,
    LedgerVerification,
)
from groundtruth.platform.auth.authz import (
    AccessContext,
    Action,
    Capability,
    ProjectAccess,
    level_allows,
    require_org_action,
    require_project,
)
from groundtruth.platform.auth.deps import resolve_sessions
from groundtruth.platform.projects import service

router = APIRouter(tags=["audit-ledger"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ApiErrorBody, "description": "Not signed in."},
    403: {"model": ApiErrorBody, "description": "Your role does not allow this."},
    404: {"model": ApiErrorBody, "description": "Unknown project."},
}


def ledger_for(request: Request) -> AuditLedger:
    """The ledger over the same database the request's store uses."""
    return AuditLedger(resolve_sessions(request))


Reader = Annotated[ProjectAccess, Depends(require_project(Capability.OVERVIEW))]
Viewer = Annotated[AccessContext, Depends(require_org_action(Action.VIEW_ORG))]

LedgerStatus = Literal["empty", "verified", "failed", "legacy_unverifiable"]

LIMITATIONS = (
    "Records are recomputed from stored content and chained to each other. The ledger is not "
    "externally timestamped or digitally signed, so it detects alteration, deletion and "
    "reordering but cannot by itself prove when a record was written."
)


class LedgerRecordView(BaseModel):
    record_id: str
    sequence: int | None
    record_kind: str
    timestamp: str
    git_commit_sha: str
    merkle_root_hash: str
    prev_root_hash: str | None
    report_version: str
    report_sha256: str | None = Field(
        default=None, description="SHA-256 of the sealed report file, for report records."
    )


class LedgerFailureView(BaseModel):
    record_id: str | None
    sequence: int | None
    reason: str


class LedgerView(BaseModel):
    project_id: str
    status: LedgerStatus
    message: str
    record_count: int
    legacy_record_count: int
    head_sequence: int | None
    head_record_id: str | None
    ledger_root: str | None
    verified_at: str
    durable: bool = Field(description="True when records are stored in the database.")
    failures: list[LedgerFailureView]
    records: list[LedgerRecordView]
    limitations: str = LIMITATIONS


class VerifyReportForm(BaseModel):
    """Multipart fields of a report check (a named model keeps the OpenAPI name plain)."""

    record_id: str = Field(min_length=1, max_length=128)
    file: UploadFile = Field(description="The report file to check (the ZIP you were given).")


class VerifyReportResult(BaseModel):
    verified: bool
    message: str
    record_id: str


class SealedReportView(BaseModel):
    record_id: str
    sequence: int | None
    timestamp: str
    report_kind: str
    report_sha256: str | None
    size_bytes: int | None


class ReportLedgerSummary(BaseModel):
    status: LedgerStatus
    message: str
    record_count: int
    ledger_root: str | None
    head_record_id: str | None
    verified_at: str


class ReportEntry(BaseModel):
    project_id: str
    project_slug: str
    project_name: str
    data_mode: str
    access_level: str
    dossier_available: bool = Field(
        description="True when the caller's access level may download the technical dossier."
    )
    dossier_path: str | None
    dossier_note: str
    last_sealed: SealedReportView | None
    ledger: ReportLedgerSummary


class ReportsView(BaseModel):
    organization_slug: str
    reports: list[ReportEntry]


def _record_view(rec: AuditRecord) -> LedgerRecordView:
    sha = rec.final_findings.get("report_sha256") if rec.record_kind == KIND_REPORT_SEALED else None
    return LedgerRecordView(
        record_id=rec.record_id,
        sequence=rec.sequence,
        record_kind=rec.record_kind,
        timestamp=rec.timestamp,
        git_commit_sha=rec.git_commit_sha,
        merkle_root_hash=rec.merkle_root_hash,
        prev_root_hash=rec.prev_root_hash,
        report_version=rec.report_version,
        report_sha256=sha if isinstance(sha, str) else None,
    )


def _failures(result: LedgerVerification) -> list[LedgerFailureView]:
    return [
        LedgerFailureView(record_id=f.record_id, sequence=f.sequence, reason=f.reason)
        for f in result.failures
    ]


@router.get(
    "/projects/{project_id}/ledger",
    response_model=LedgerView,
    summary="The project's audit ledger, verified on read",
    responses=_ERRORS,
)
def get_project_ledger(request: Request, access: Reader) -> LedgerView:
    ledger = ledger_for(request)
    project_id = access.project.id
    result = ledger.verify_project(project_id)
    records = ledger.get_records(project_id)
    return LedgerView(
        project_id=project_id,
        status=result.status,  # type: ignore[arg-type]
        message=result.message,
        record_count=result.record_count,
        legacy_record_count=result.legacy_record_count,
        head_sequence=result.head_sequence,
        head_record_id=result.head_record_id,
        ledger_root=result.ledger_root,
        verified_at=result.verified_at,
        durable=ledger.durable,
        failures=_failures(result),
        records=[_record_view(r) for r in records],
    )


MAX_REPORT_VERIFY_BYTES = 25 * 1024 * 1024
_READ_CHUNK_BYTES = 1024 * 1024


async def _read_bounded_upload(file: UploadFile, max_bytes: int | None = None) -> bytes:
    limit = MAX_REPORT_VERIFY_BYTES if max_bytes is None else max_bytes
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_READ_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise HTTPException(
                status_code=413,
                detail={
                    "code": "payload_too_large",
                    "message": (
                        f"Uploaded report exceeds maximum size of {limit // (1024 * 1024)} MB."
                    ),
                    "hint": None,
                },
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.post(
    "/projects/{project_id}/ledger/verify-report",
    response_model=VerifyReportResult,
    summary="Check that a file is exactly the report a ledger record sealed",
    responses=_ERRORS,
)
async def verify_report(
    request: Request,
    access: Reader,
    form: Annotated[VerifyReportForm, Form()],
) -> VerifyReportResult:
    record_id, file = form.record_id, form.file
    ledger = ledger_for(request)
    rec = ledger.get_record_by_id(record_id)
    # A record from another project is reported exactly like a missing one.
    if rec is None or rec.project_id != access.project.id:
        return VerifyReportResult(
            verified=False,
            message="No sealing record with that id exists for this project.",
            record_id=record_id,
        )
    content = await _read_bounded_upload(file)
    ok, message = ledger.verify_report(record_id, content)
    audit(
        request,
        access.ctx,
        action="ledger.verify_report",
        resource_type="project",
        resource_id=access.project.id,
        details={"record_id": record_id, "verified": ok},
    )
    return VerifyReportResult(verified=ok, message=message, record_id=record_id)


class ReproducibilityRequest(BaseModel):
    record_id: str = Field(min_length=1, max_length=128)
    recomputed_findings: dict[str, Any]


class ReproducibilityResult(BaseModel):
    record_id: str
    reproducibility_verified: bool
    message: str


@router.post(
    "/projects/{project_id}/ledger/verify-reproducibility",
    response_model=ReproducibilityResult,
    summary="Compare re-run findings with the findings a ledger record stored",
    responses=_ERRORS,
)
def verify_reproducibility(
    body: ReproducibilityRequest, request: Request, access: Reader
) -> ReproducibilityResult:
    ledger = ledger_for(request)
    rec = ledger.get_record_by_id(body.record_id)
    if rec is None or rec.project_id != access.project.id:
        return ReproducibilityResult(
            record_id=body.record_id,
            reproducibility_verified=False,
            message="No record with that id exists for this project.",
        )
    ok = ledger.verify_reproducibility(body.record_id, body.recomputed_findings)
    return ReproducibilityResult(
        record_id=body.record_id,
        reproducibility_verified=ok,
        message=(
            "Every finding present in both the record and the re-run is identical."
            if ok
            else "The re-run differs from the recorded findings, or shares no findings with them."
        ),
    )


@router.get(
    "/orgs/{slug}/reports",
    response_model=ReportsView,
    summary="Reports the organization can download, with their real ledger state",
    responses={**_ERRORS, 503: {"model": ApiErrorBody, "description": "No database."}},
)
def list_reports(slug: str, request: Request, ctx: Viewer) -> ReportsView:
    ledger = ledger_for(request)
    entries: list[ReportEntry] = []
    with resolve_sessions(request)() as db:
        items = service.list_org_projects(db, ctx)
    verified_by_project = ledger.verify_projects([p.id for p, _ in items])
    for project, level in items:
        verification, records = verified_by_project[project.id]
        sealed = [
            r for r in records if r.record_kind == KIND_REPORT_SEALED and r.hash_scheme is not None
        ]
        last = sealed[-1] if sealed else None
        can_export = level_allows(level, Capability.DOSSIER_EXPORT)
        entries.append(
            ReportEntry(
                project_id=project.id,
                project_slug=project.slug,
                project_name=project.name,
                data_mode=project.data_mode,
                access_level=level.value,
                dossier_available=can_export,
                dossier_path=f"/projects/{project.id}/export/dossier" if can_export else None,
                dossier_note=(
                    "Technical dossier (ZIP of JSON/CSV with a checksum manifest) for audit use. "
                    "It is not a stakeholder summary report."
                    if can_export
                    else "Your access level does not include the technical dossier."
                ),
                last_sealed=(
                    SealedReportView(
                        record_id=last.record_id,
                        sequence=last.sequence,
                        timestamp=last.timestamp,
                        report_kind=str(
                            last.final_findings.get("report_kind", last.report_version)
                        ),
                        report_sha256=last.final_findings.get("report_sha256"),
                        size_bytes=last.final_findings.get("report_size_bytes"),
                    )
                    if last
                    else None
                ),
                ledger=ReportLedgerSummary(
                    status=verification.status,  # type: ignore[arg-type]
                    message=verification.message,
                    record_count=verification.record_count,
                    ledger_root=verification.ledger_root,
                    head_record_id=verification.head_record_id,
                    verified_at=verification.verified_at,
                ),
            )
        )
    return ReportsView(organization_slug=slug, reports=entries)
