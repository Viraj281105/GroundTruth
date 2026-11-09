"""Project documents: validation, storage and honest text extraction.

An upload is stored and hashed; that is all ``uploaded`` means. Text extraction runs only for
plain-text types (PDF has no installed text dependency, so it is stored only). The claims
extractor yields *candidates* (text spans); nothing here verifies anything.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from groundtruth.platform.config import get_settings
from groundtruth.platform.storage.blob_store import (
    StorageBackend,
    StorageTier,
    get_storage_backend,
)
from groundtruth.platform.store.models import ProjectDocumentRow

ALLOWED_TYPES: dict[str, str] = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".csv": "text/csv",
}
"""Extension -> the content type we record (the client's declared type is never trusted)."""
TEXT_EXTRACTABLE = frozenset({".txt", ".md"})
MAX_EXTRACT_CHARS = 1_000_000
MAX_CANDIDATES = 500
PROCESSING_NOTE = (
    "Stored and checksummed. A document is not evidence of any claim until independently "
    "checked; extracted claim candidates are text matches, not verified facts."
)


class DocumentRejectedError(Exception):
    """An upload that fails validation: ``status`` is the HTTP status, ``code`` the error code."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


@dataclass(frozen=True)
class Extraction:
    status: str
    detail: str
    text: str | None = None


def max_bytes() -> int:
    return get_settings().project_document_max_bytes


def sanitise_filename(raw: str | None) -> str:
    """A display-safe file name: no directories, no control or odd characters, bounded length."""
    name = (raw or "").replace("\\", "/").split("/")[-1]
    name = re.sub(r"[\x00-\x1f\x7f]", "", name)
    name = re.sub(r"[^\w.\- ()]", "_", name, flags=re.UNICODE)
    name = re.sub(r"\.{2,}", ".", name).strip(" .")
    return name[:200] or "document"


def validate_upload(raw_name: str | None, data: bytes) -> tuple[str, str, str]:
    """``(safe_name, extension, content_type)`` or raise ``DocumentRejectedError``."""
    safe = sanitise_filename(raw_name)
    ext = PurePosixPath(safe).suffix.lower()
    if ext not in ALLOWED_TYPES:
        raise DocumentRejectedError(
            415,
            "unsupported_document_type",
            f"File type {ext or '(none)'} is not accepted. Upload one of: "
            f"{', '.join(sorted(ALLOWED_TYPES))}.",
        )
    if not data:
        raise DocumentRejectedError(422, "empty_document", "The uploaded file is empty.")
    limit = max_bytes()
    if len(data) > limit:
        raise DocumentRejectedError(
            413,
            "document_too_large",
            f"The file is larger than the {limit} byte limit ({limit / (1024 * 1024):.1f} MB).",
        )
    if ext == ".pdf" and data.lstrip()[:5] != b"%PDF-":
        raise DocumentRejectedError(
            422, "invalid_document", "The file is named .pdf but is not a PDF document."
        )
    if ext != ".pdf" and b"\x00" in data[:8192]:
        raise DocumentRejectedError(
            422, "invalid_document", f"The file is named {ext} but looks like binary data."
        )
    return safe, ext, ALLOWED_TYPES[ext]


def _pdf_text_available() -> bool:
    for mod in ("pypdf", "PyPDF2", "pdfplumber", "fitz"):
        try:
            __import__(mod)
        except ImportError:
            continue
        return True
    return False


def extract_text(ext: str, data: bytes) -> Extraction:
    """Bounded synchronous text extraction. Never raises."""
    if ext in TEXT_EXTRACTABLE:
        text = data.decode("utf-8", errors="replace")
        note = "Plain text read."
        if len(text) > MAX_EXTRACT_CHARS:
            text = text[:MAX_EXTRACT_CHARS]
            note = f"Plain text read; truncated to the first {MAX_EXTRACT_CHARS} characters."
        return Extraction("text_extracted", note, text)
    if ext == ".pdf":
        if not _pdf_text_available():
            return Extraction(
                "extraction_unsupported",
                "Stored only. This server has no PDF text extraction, so nothing was read "
                "from the PDF. Upload a .txt or .md copy to get claim candidates.",
            )
        return Extraction(
            "extraction_unsupported",
            "Stored only. PDF text extraction is not wired into this build.",
        )
    return Extraction(
        "extraction_unsupported",
        f"Stored only. {ext} files are kept as records and are not parsed for claims.",
    )


def claim_candidates(text: str, doc_id: str) -> list[dict[str, Any]]:
    """Claim candidates (verbatim text spans) from the statement analyser.

    These are text matches only. Over-claims (absolute wording such as "proves" or "fully
    recovered") are included and keep their kind, so a reader sees them. Nothing is verified.
    """
    from groundtruth.claims.statements import analyze_text

    out: list[dict[str, Any]] = []
    for st in analyze_text(text, doc_id).statements[:MAX_CANDIDATES]:
        out.append(
            {
                "kind": getattr(st.kind, "value", str(st.kind)),
                "value": st.value,
                "unit": st.unit,
                "start": st.start,
                "end": st.end,
                "quote": st.text,
                "period": st.period,
                "status": getattr(st.status, "value", str(st.status)),
                "reason": st.reason,
                "evidence_gap": st.evidence_gap,
            }
        )
    return out


def blob_store() -> StorageBackend:
    return get_storage_backend(base_dir=get_settings().project_documents_dir)


def storage_key(project_id: str, doc_id: str) -> str:
    return f"project-documents/{project_id}/{doc_id}"


def create_document(
    db: Session,
    *,
    project_id: str,
    user_id: str,
    safe_name: str,
    ext: str,
    content_type: str,
    data: bytes,
) -> ProjectDocumentRow:
    """Store the bytes, run honest extraction and add the row (the caller commits)."""
    doc_id = str(uuid.uuid4())
    key = storage_key(project_id, doc_id)
    sha = hashlib.sha256(data).hexdigest()
    blob_store().put_bytes(
        StorageTier.RAW_SOURCE,
        key,
        data,
        content_type=content_type,
        metadata={"project_id": project_id, "sha256": sha},
    )
    result = extract_text(ext, data)
    chars: int | None = None
    claims: int | None = None
    status, detail = result.status, result.detail
    if result.text is not None:
        try:
            chars = len(result.text)
            claims = len(claim_candidates(result.text, doc_id))
        except Exception as exc:
            status = "extraction_failed"
            detail = f"Claim extraction failed ({type(exc).__name__}); the file is stored."
            chars = claims = None
    row = ProjectDocumentRow(
        id=doc_id,
        project_id=project_id,
        original_filename=safe_name,
        content_type=content_type,
        size_bytes=len(data),
        sha256=sha,
        storage_key=key,
        uploaded_by=user_id,
        uploaded_at=datetime.now(UTC),
        status=status,
        status_detail=detail,
        extracted_text_chars=chars,
        extracted_claims_count=claims,
    )
    db.add(row)
    db.flush()
    return row


def list_documents(db: Session, project_id: str) -> list[ProjectDocumentRow]:
    return list(
        db.execute(
            select(ProjectDocumentRow)
            .where(ProjectDocumentRow.project_id == project_id)
            .where(ProjectDocumentRow.deleted_at.is_(None))
            .order_by(ProjectDocumentRow.uploaded_at, ProjectDocumentRow.id)
        ).scalars()
    )


def get_document(db: Session, project_id: str, doc_id: str) -> ProjectDocumentRow | None:
    """A live (not deleted) document of exactly this project, else ``None``."""
    return db.execute(
        select(ProjectDocumentRow)
        .where(ProjectDocumentRow.id == doc_id)
        .where(ProjectDocumentRow.project_id == project_id)
        .where(ProjectDocumentRow.deleted_at.is_(None))
    ).scalar_one_or_none()


def document_dict(row: ProjectDocumentRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "filename": row.original_filename,
        "content_type": row.content_type,
        "size_bytes": row.size_bytes,
        "sha256": row.sha256,
        "uploaded_by": row.uploaded_by,
        "uploaded_at": row.uploaded_at,
        "status": row.status,
        "status_detail": row.status_detail,
        "extracted_text_chars": row.extracted_text_chars,
        "extracted_claims_count": row.extracted_claims_count,
    }


def status_counts(rows: list[ProjectDocumentRow]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        out[r.status] = out.get(r.status, 0) + 1
    return out
