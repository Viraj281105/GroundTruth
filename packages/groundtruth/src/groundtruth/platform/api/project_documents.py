"""Project document routes: upload, list, download, extraction candidates and soft delete.

Every route resolves the project through ``require_project`` (404 for no access, 403 for too
low a level), so documents are tenant-scoped exactly like the rest of the project. An upload is
*stored*, nothing more: ``status`` says whether any text was read, and no route ever marks a
document, or a claim found in it, as verified.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from groundtruth.platform.api.errors import ApiErrorBody
from groundtruth.platform.api.project_schemas import DocumentSummary
from groundtruth.platform.api.scope import audit
from groundtruth.platform.auth.authz import Action, Capability, ProjectAccess, require_project
from groundtruth.platform.auth.deps import resolve_sessions
from groundtruth.platform.auth.service import auth_error
from groundtruth.platform.projects import documents as docs
from groundtruth.platform.storage.blob_store import StorageTier

router = APIRouter(tags=["project-documents"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ApiErrorBody, "description": "Not signed in."},
    403: {"model": ApiErrorBody, "description": "Your access level or role does not allow this."},
    404: {"model": ApiErrorBody, "description": "Unknown project or document."},
    503: {"model": ApiErrorBody, "description": "No database is configured."},
}
_UPLOAD_ERRORS: dict[int | str, dict[str, Any]] = {
    **_ERRORS,
    413: {"model": ApiErrorBody, "description": "The file is larger than the size limit."},
    415: {"model": ApiErrorBody, "description": "File type not accepted."},
    422: {"model": ApiErrorBody, "description": "Empty or invalid file."},
}

Viewer = Annotated[ProjectAccess, Depends(require_project(Capability.OVERVIEW))]
Editor = Annotated[
    ProjectAccess, Depends(require_project(Capability.EDIT, action=Action.EDIT_PROJECT))
]


class DocumentUploadForm(BaseModel):
    """The multipart field of a document upload (a named model keeps the OpenAPI name plain)."""

    file: UploadFile = Field(description="The document: .pdf, .txt, .md or .csv.")


class DocumentView(DocumentSummary):
    project_id: str
    uploaded_by: str | None = None
    extracted_text_chars: int | None = None
    processing_note: str = docs.PROCESSING_NOTE


class DocumentListView(BaseModel):
    project_id: str
    documents: list[DocumentView]
    counts: dict[str, int] = Field(description="Documents per status; absent statuses are 0.")
    max_bytes: int
    allowed_extensions: list[str]


class ClaimCandidate(BaseModel):
    kind: str
    value: float | None = None
    unit: str | None = None
    start: int | None = None
    end: int | None = None
    quote: str | None = None


class ExtractionView(BaseModel):
    document_id: str
    status: Literal["text_extracted"]
    claims_count: int
    candidates: list[ClaimCandidate]
    verified: Literal[False] = Field(
        default=False, description="Candidates are text matches; none is verified."
    )
    note: str = docs.PROCESSING_NOTE


def _view(row: Any) -> DocumentView:
    return DocumentView(**docs.document_dict(row))


def _not_found() -> Exception:
    return auth_error("not_found", "Document not found.")


def _reject(exc: docs.DocumentRejectedError) -> Exception:
    from fastapi import HTTPException

    return HTTPException(
        status_code=exc.status,
        detail={"code": exc.code, "message": exc.message, "hint": None},
    )


@router.post(
    "/projects/{project_id}/documents",
    response_model=DocumentView,
    status_code=201,
    summary="Upload a project document (.pdf, .txt, .md, .csv; multipart field `file`)",
    responses=_UPLOAD_ERRORS,
)
def upload_document(
    request: Request, access: Editor, form: Annotated[DocumentUploadForm, Form()]
) -> DocumentView:
    """Stores the file and its sha256. `status` is `uploaded` until text is read: `.txt`/`.md`
    become `text_extracted` (claim candidates counted, never verified); other types are
    `extraction_unsupported` with the reason in `status_detail`."""
    file = form.file
    limit = docs.max_bytes()
    data = file.file.read(limit + 1)
    try:
        safe, ext, content_type = docs.validate_upload(file.filename, data)
    except docs.DocumentRejectedError as exc:
        raise _reject(exc) from exc
    store = docs.blob_store()
    with resolve_sessions(request)() as db:
        row = docs.create_document(
            db,
            project_id=access.project.id,
            user_id=access.ctx.user_id,
            safe_name=safe,
            ext=ext,
            content_type=content_type,
            data=data,
        )
        try:
            db.commit()
        except Exception:
            db.rollback()
            store.delete(StorageTier.RAW_SOURCE, row.storage_key)
            raise
        view = _view(row)
    audit(
        request,
        access.ctx,
        action="document.upload",
        resource_type="project_document",
        resource_id=view.id,
        details={
            "project_id": access.project.id,
            "filename": view.filename,
            "sha256": view.sha256,
            "size_bytes": view.size_bytes,
            "status": view.status,
        },
    )
    return view


@router.get(
    "/projects/{project_id}/documents",
    response_model=DocumentListView,
    summary="Documents uploaded to the project, with processing status",
    responses=_ERRORS,
)
def list_documents(request: Request, access: Viewer) -> DocumentListView:
    with resolve_sessions(request)() as db:
        rows = docs.list_documents(db, access.project.id)
        return DocumentListView(
            project_id=access.project.id,
            documents=[_view(r) for r in rows],
            counts=docs.status_counts(rows),
            max_bytes=docs.max_bytes(),
            allowed_extensions=sorted(docs.ALLOWED_TYPES),
        )


@router.get(
    "/projects/{project_id}/documents/{doc_id}/download",
    summary="The original uploaded bytes",
    responses={
        200: {"content": {"application/octet-stream": {"schema": {"type": "string"}}}},
        **_ERRORS,
        409: {"model": ApiErrorBody, "description": "The stored copy failed its checksum."},
    },
)
def download_document(doc_id: str, request: Request, access: Viewer) -> Response:
    with resolve_sessions(request)() as db:
        row = docs.get_document(db, access.project.id, doc_id)
        if row is None:
            raise _not_found()
        key, sha, name, ctype = row.storage_key, row.sha256, row.original_filename, row.content_type
    try:
        data = docs.blob_store().get_bytes(StorageTier.RAW_SOURCE, key)
    except FileNotFoundError as exc:
        raise auth_error("not_found", "The stored file is no longer available.") from exc
    if hashlib.sha256(data).hexdigest() != sha:
        raise auth_error("conflict", "The stored file no longer matches its recorded checksum.")
    audit(
        request,
        access.ctx,
        action="document.download",
        resource_type="project_document",
        resource_id=doc_id,
        details={"project_id": access.project.id, "filename": name, "sha256": sha},
    )
    ascii_name = name.encode("ascii", "replace").decode().replace("?", "_").replace('"', "_")
    return Response(
        content=data,
        media_type=ctype,
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}"
            ),
            "X-Content-Type-Options": "nosniff",
            "X-GroundTruth-SHA256": sha,
        },
    )


@router.get(
    "/projects/{project_id}/documents/{doc_id}/extraction",
    response_model=ExtractionView,
    summary="Claim candidates found in the document text (not verified)",
    responses={
        **_ERRORS,
        409: {"model": ApiErrorBody, "description": "No text was extracted from this document."},
    },
)
def document_extraction(doc_id: str, request: Request, access: Viewer) -> ExtractionView:
    """Only for `text_extracted` documents. Anything else answers 409 with the reason in
    `detail.message`. Candidates are regular-expression matches with their text spans."""
    with resolve_sessions(request)() as db:
        row = docs.get_document(db, access.project.id, doc_id)
        if row is None:
            raise _not_found()
        status, detail, key, sha = row.status, row.status_detail, row.storage_key, row.sha256
    if status != "text_extracted":
        from fastapi import HTTPException

        raise HTTPException(
            status_code=409,
            detail={
                "code": "extraction_not_available",
                "message": f"No text was extracted ({status}). {detail or ''}".strip(),
                "hint": None,
            },
        )
    try:
        data = docs.blob_store().get_bytes(StorageTier.RAW_SOURCE, key)
    except FileNotFoundError as exc:
        raise auth_error("not_found", "The stored file is no longer available.") from exc
    if hashlib.sha256(data).hexdigest() != sha:
        raise auth_error("conflict", "The stored file no longer matches its recorded checksum.")
    text = docs.extract_text(".txt", data).text or ""
    candidates = docs.claim_candidates(text, doc_id)
    return ExtractionView(
        document_id=doc_id,
        status="text_extracted",
        claims_count=len(candidates),
        candidates=[ClaimCandidate(**c) for c in candidates],
    )


@router.delete(
    "/projects/{project_id}/documents/{doc_id}",
    status_code=204,
    summary="Soft-delete a document (the record and audit trail remain)",
    responses=_ERRORS,
)
def delete_document(doc_id: str, request: Request, access: Editor) -> Response:
    with resolve_sessions(request)() as db:
        row = docs.get_document(db, access.project.id, doc_id)
        if row is None:
            raise _not_found()
        row.deleted_at = datetime.now(UTC)
        key, name, sha = row.storage_key, row.original_filename, row.sha256
        db.commit()
    docs.blob_store().delete(StorageTier.RAW_SOURCE, key)
    audit(
        request,
        access.ctx,
        action="document.delete",
        resource_type="project_document",
        resource_id=doc_id,
        details={"project_id": access.project.id, "filename": name, "sha256": sha},
    )
    return Response(status_code=204)
