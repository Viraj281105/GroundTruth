"""Project claims: statements a person chose to verify, matched against the evidence on file.

The workflow is deliberately manual at the decision points:

1. A document is uploaded and its text read; the analyser proposes *candidate* statements.
2. A person reviews a candidate, corrects it if the extraction misread it, and **promotes** it.
   Nothing is ever promoted automatically, and a candidate is never a finding.
3. The promoted claim is matched against the evidence the platform holds (the project boundary,
   ingested satellite observations) and gets one of four outcomes: supported, partially supported,
   contradicted, or insufficiently evidenced, each with its reasons and gaps.

What the extractor read (``original_*``, the source document, its checksum and the character span)
is stored once and never changed. Corrections go in the unprefixed fields, so a reviewer can always
see both what the document said and what was actually tested.
"""

from __future__ import annotations

import dataclasses
import hashlib
import math
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from groundtruth.claims.evidence_match import (
    ClaimOutcome,
    EvidenceContext,
    ObservationSeries,
    match_claim,
)
from groundtruth.claims.statements import StatementKind, analyze_text
from groundtruth.platform.projects import documents as docs
from groundtruth.platform.projects.data import load_observations
from groundtruth.platform.storage.blob_store import StorageTier
from groundtruth.platform.store.models import ProjectClaimRow, ProjectDocumentRow, ProjectRow

ALLOWED_KINDS: tuple[str, ...] = tuple(k.value for k in StatementKind)
MAX_STATEMENT_CHARS = 1000
MAX_ACTIVE_CLAIMS = 100

# The workbench groups claims by these eight restoration dimensions (claims.verification_engine).
KIND_TO_STRUCTURED: dict[str, str] = {
    "area_hectares": "area_restored",
    "survival_rate": "tree_survival",
    "vegetation_index_change": "vegetation_improvement",
    "carbon_tco2e": "carbon_sequestration",
    "index_to_carbon_conflation": "carbon_sequestration",
    "biodiversity_recovery": "biodiversity_improvement",
    "ecosystem_recovery": "ecosystem_recovery",
    "unsupported_conclusion": "ecosystem_recovery",
    "causal_attribution": "vegetation_improvement",
}


class ClaimInputError(ValueError):
    """A claim request that cannot be accepted; ``message`` and ``hint`` are safe to show."""

    def __init__(self, code: str, message: str, hint: str | None = None, status: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint
        self.status = status


def _now() -> datetime:
    return datetime.now(UTC)


# --- reading a source document ------------------------------------------------------------------


def read_document_text(
    db: Session, project_id: str, document_id: str
) -> tuple[ProjectDocumentRow, str]:
    """The extracted text of a stored document, re-read from its stored bytes.

    The bytes are checked against the recorded SHA-256 first, so a claim can only ever point into
    the exact file that was uploaded.
    """
    row = docs.get_document(db, project_id, document_id)
    if row is None:
        raise ClaimInputError(
            "document_not_found", "That document was not found in this project.", status=404
        )
    if row.status != "text_extracted":
        raise ClaimInputError(
            "document_not_readable",
            f"No text was extracted from this document ({row.status}), so no statement can be taken from it.",
            "Upload a .txt or .md version, or add the claim manually.",
            status=409,
        )
    try:
        data = docs.blob_store().get_bytes(StorageTier.RAW_SOURCE, row.storage_key)
    except FileNotFoundError:
        raise ClaimInputError(
            "document_missing", "The stored file is no longer available.", status=409
        ) from None
    if hashlib.sha256(data).hexdigest() != row.sha256:
        raise ClaimInputError(
            "document_changed",
            "The stored file no longer matches its recorded checksum, so it cannot be used as a source.",
            status=409,
        )
    return row, docs.extract_text(".txt", data).text or ""


# --- validation helpers -----------------------------------------------------------------------------


def _number(value: Any, label: str) -> float | None:
    if value is None or value == "":
        return None
    try:
        x = float(value)
    except (TypeError, ValueError):
        raise ClaimInputError("invalid_claim", f"{label} must be a number.") from None
    if not math.isfinite(x):
        raise ClaimInputError("invalid_claim", f"{label} must be a finite number.")
    return x


def _text(value: Any, label: str, limit: int, *, required: bool = False) -> str | None:
    if value is None or str(value).strip() == "":
        if required:
            raise ClaimInputError("invalid_claim", f"{label} is required.")
        return None
    s = " ".join(str(value).split())
    if len(s) > limit:
        raise ClaimInputError("invalid_claim", f"{label} must be at most {limit} characters.")
    return s


def _kind(value: Any) -> str:
    k = str(value or "").strip()
    if k not in ALLOWED_KINDS:
        raise ClaimInputError(
            "invalid_claim",
            f"Unknown claim type {k!r}.",
            "Choose one of: " + ", ".join(ALLOWED_KINDS) + ".",
        )
    return k


# --- create / edit / withdraw ---------------------------------------------------------------------------


def create_claim(
    db: Session, project: ProjectRow, user_id: str | None, payload: dict[str, Any]
) -> ProjectClaimRow:
    """Promote a candidate statement from a document, or add a claim typed by the user.

    With ``document_id`` + ``start``/``end`` the source is re-read from the stored file and the span
    must be a statement the analyser really found there; what it read is stored as the immutable
    ``original_*`` fields. Edits in the payload (``statement_text``, ``kind``, ``value``, ``unit``,
    ``period``) only change the editable fields.
    """
    active = db.execute(
        sa.select(sa.func.count())
        .select_from(ProjectClaimRow)
        .where(ProjectClaimRow.project_id == project.id, ProjectClaimRow.withdrawn_at.is_(None))
    ).scalar_one()
    if active >= MAX_ACTIVE_CLAIMS:
        raise ClaimInputError(
            "too_many_claims",
            f"A project can hold at most {MAX_ACTIVE_CLAIMS} active claims.",
            "Withdraw claims you no longer need.",
            status=409,
        )

    doc_id = payload.get("document_id")
    src: dict[str, Any] = {}
    defaults: tuple[str | None, float | None, str | None, str | None]
    if doc_id:
        start, end = payload.get("start"), payload.get("end")
        if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end <= start:
            raise ClaimInputError(
                "invalid_claim",
                "A document source needs the start and end positions of the statement.",
            )
        doc_row, text = read_document_text(db, project.id, str(doc_id))
        analysis = analyze_text(text, str(doc_id))
        stmt = next((s for s in analysis.statements if s.start == start and s.end == end), None)
        if stmt is None:
            raise ClaimInputError(
                "source_not_found",
                "No extracted statement exists at that position in the document.",
                "Open 'View extracted statements' and promote one of those, or add the claim manually.",
                status=409,
            )
        dup = db.execute(
            sa.select(ProjectClaimRow.id).where(
                ProjectClaimRow.project_id == project.id,
                ProjectClaimRow.source_document_id == doc_row.id,
                ProjectClaimRow.source_start == start,
                ProjectClaimRow.source_end == end,
                ProjectClaimRow.withdrawn_at.is_(None),
            )
        ).first()
        if dup is not None:
            raise ClaimInputError(
                "already_promoted",
                "This statement has already been added as a claim.",
                "Edit the existing claim instead.",
                status=409,
            )
        src = {
            "source_document_id": doc_row.id,
            "source_document_name": doc_row.original_filename,
            "source_document_sha256": doc_row.sha256,
            "source_start": start,
            "source_end": end,
            "original_text": text[start:end],  # taken from the file, never from the request
            "original_kind": stmt.kind.value,
            "original_value": stmt.value,
            "original_unit": stmt.unit,
            "original_period": stmt.period,
        }
        defaults = (stmt.kind.value, stmt.value, stmt.unit, stmt.period)
    else:
        typed = _text(
            payload.get("statement_text"), "The claim", MAX_STATEMENT_CHARS, required=True
        )
        assert typed is not None
        if len(typed) < 5:
            raise ClaimInputError("invalid_claim", "The claim is too short to be meaningful.")
        src = {
            "source_document_id": None,
            "source_document_name": None,
            "source_document_sha256": None,
            "source_start": None,
            "source_end": None,
            "original_text": typed,
            "original_kind": None,
            "original_value": None,
            "original_unit": None,
            "original_period": None,
        }
        defaults = (None, None, None, None)

    kind = _kind(payload["kind"] if payload.get("kind") else defaults[0])
    value = _number(
        payload["value"] if "value" in payload and payload["value"] is not None else defaults[1],
        "The value",
    )
    unit = _text(payload["unit"] if payload.get("unit") else defaults[2], "The unit", 40)
    period = _text(payload["period"] if payload.get("period") else defaults[3], "The period", 60)
    statement = (
        _text(payload.get("statement_text"), "The claim", MAX_STATEMENT_CHARS)
        or src["original_text"]
    )

    row = ProjectClaimRow(
        id=str(uuid.uuid4()),
        project_id=project.id,
        statement_text=str(statement)[:MAX_STATEMENT_CHARS],
        kind=kind,
        claimed_value=value,
        claimed_unit=unit,
        claimed_period=period,
        created_by=user_id,
        created_at=_now(),
        **src,
    )
    db.add(row)
    db.flush()
    return row


def update_claim(
    db: Session, row: ProjectClaimRow, user_id: str | None, patch: dict[str, Any]
) -> ProjectClaimRow:
    """Correct the editable fields. The original extraction and its source are never touched."""
    if row.withdrawn_at is not None:
        raise ClaimInputError("claim_withdrawn", "A withdrawn claim cannot be edited.", status=409)
    if "statement_text" in patch:
        row.statement_text = (
            _text(patch["statement_text"], "The claim", MAX_STATEMENT_CHARS, required=True)
            or row.statement_text
        )
    if "kind" in patch:
        row.kind = _kind(patch["kind"])
    if "value" in patch:
        row.claimed_value = _number(patch["value"], "The value")
    if "unit" in patch:
        row.claimed_unit = _text(patch["unit"], "The unit", 40)
    if "period" in patch:
        row.claimed_period = _text(patch["period"], "The period", 60)
    row.updated_by = user_id
    row.updated_at = _now()
    return row


def withdraw_claim(row: ProjectClaimRow, user_id: str | None) -> None:
    row.withdrawn_at = _now()
    row.updated_by = user_id
    row.updated_at = row.withdrawn_at


def list_claims(
    db: Session, project_id: str, *, include_withdrawn: bool = False
) -> list[ProjectClaimRow]:
    q = sa.select(ProjectClaimRow).where(ProjectClaimRow.project_id == project_id)
    if not include_withdrawn:
        q = q.where(ProjectClaimRow.withdrawn_at.is_(None))
    return list(db.execute(q.order_by(ProjectClaimRow.created_at, ProjectClaimRow.id)).scalars())


def get_claim(db: Session, project_id: str, claim_id: str) -> ProjectClaimRow | None:
    row = db.get(ProjectClaimRow, claim_id)
    return row if row is not None and row.project_id == project_id else None


def is_edited(row: ProjectClaimRow) -> bool:
    """Whether the tested claim differs from what was originally extracted (or typed)."""
    if row.original_kind is None:  # typed by a user: there is no extractor reading to compare with
        return row.statement_text != row.original_text
    return (
        row.statement_text != row.original_text
        or row.kind != row.original_kind
        or row.claimed_value != row.original_value
        or row.claimed_unit != row.original_unit
        or row.claimed_period != row.original_period
    )


# --- matching ---------------------------------------------------------------------------------------------


def build_evidence_context(project: ProjectRow, data_dir: Path) -> EvidenceContext:
    """What the platform holds for this project right now, taken only from stored artefacts."""
    from groundtruth.platform.projects.assessment import _read_boundary
    from groundtruth.platform.projects.boundary import _area_ha

    area: float | None = None
    geom = _read_boundary(project)
    if geom is not None:
        area = float(_area_ha(geom))
    series: dict[str, ObservationSeries] = {}
    for ind in ("ndvi", "evi", "ndmi", "nbr"):
        res = load_observations(project, ind, data_dir=data_dir)
        if res.status != "available" or res.bundle is None:
            continue
        values: dict[int, float] = {}
        cov: dict[int, float | None] = {}
        for r in res.bundle.records:
            if r.evidence_state == "UNAVAILABLE" or math.isnan(r.value):
                continue
            values[r.year] = float(r.value)
            cov[r.year] = r.aoi_coverage_pct
        if values:
            series[ind] = ObservationSeries(
                indicator=ind,
                values=values,
                coverage_pct=cov,
                source=f"{res.bundle.catalog_url or 'Sentinel-2'} annual composite, project boundary",
            )
    return EvidenceContext(
        boundary_area_ha=area,
        boundary_ref=f"sha256:{project.boundary_sha256[:12]}…" if project.boundary_sha256 else None,
        series=series,
        treatment_start_year=project.treatment_start_year,
    )


def evaluate(
    project: ProjectRow, rows: list[ProjectClaimRow], data_dir: Path
) -> list[tuple[ProjectClaimRow, ClaimOutcome]]:
    ctx = build_evidence_context(project, data_dir)
    return [
        (r, match_claim(r.kind, r.claimed_value, r.claimed_unit, r.claimed_period, ctx))
        for r in rows
    ]


def custom_claims_for_portfolio(
    project: ProjectRow, rows: list[ProjectClaimRow], data_dir: Path
) -> list[dict[str, Any]]:
    """The promoted claims in the shape the claim-verification engine builds its portfolio from."""
    out: list[dict[str, Any]] = []
    for r, o in evaluate(project, rows, data_dir):
        src = f' in "{r.source_document_name}"' if r.source_document_name else " (typed by a user)"
        out.append(
            {
                "claim_id": r.id,
                "claim_type": KIND_TO_STRUCTURED.get(r.kind, "ecosystem_recovery"),
                "title": r.statement_text[:120],
                "definition": f'Stated{src}: "{r.original_text}"',
                "claimed_value": r.claimed_value
                if r.claimed_value is not None
                else r.statement_text,
                "claimed_unit": r.claimed_unit or "",
                "observed_value": o.observed_value,
                "observed_unit": o.observed_unit,
                "required_evidence": o.required_evidence,
                "available_evidence": o.available_evidence,
                "supporting_observations": o.supporting,
                "contradictory_observations": o.contradicting,
                "missing_evidence": o.missing_evidence,
                "methodology": o.methodology,
                "limitations": o.limitations,
                "status": o.status,
                "discrepancy_percentage": o.discrepancy_percentage,
                "headline": o.headline,
                "reasons": o.reasons,
                "statements": [
                    {
                        "statement_id": f"{r.id[:8]}-1",
                        "statement_text": r.statement_text,
                        "target_metric": r.kind,
                        "claimed_value": r.claimed_value if r.claimed_value is not None else "",
                        "observed_value": o.observed_value,
                        "status": o.status,
                        "rationale": o.headline,
                    }
                ],
                "source": source_view(r),
            }
        )
    return out


def source_view(r: ProjectClaimRow) -> dict[str, Any]:
    """Where a claim came from, for display next to its outcome."""
    return {
        "project_claim_id": r.id,
        "document_id": r.source_document_id,
        "document_name": r.source_document_name,
        "document_sha256": r.source_document_sha256,
        "start": r.source_start,
        "end": r.source_end,
        "original_text": r.original_text,
        "original_kind": r.original_kind,
        "original_value": r.original_value,
        "original_unit": r.original_unit,
        "original_period": r.original_period,
        "statement_text": r.statement_text,
        "kind": r.kind,
        "value": r.claimed_value,
        "unit": r.claimed_unit,
        "period": r.claimed_period,
        "edited": is_edited(r),
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


def report_items(
    project: ProjectRow, rows: list[ProjectClaimRow], data_dir: Path
) -> list[dict[str, Any]]:
    """Promoted claims with their source and outcome, for the technical dossier (JSON-safe)."""
    return [
        {"claim_id": r.id, "source": source_view(r), "outcome": dataclasses.asdict(o)}
        for r, o in evaluate(project, rows, data_dir)
    ]
