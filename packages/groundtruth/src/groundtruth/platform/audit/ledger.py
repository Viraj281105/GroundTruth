"""Tamper-evident audit ledger.

Every record is bound to its own content by a Merkle tree and to the records before it by a
hash chain, so a later change to a record, a deleted record or a reordering of records is
detected by :meth:`AuditLedger.verify_project`.

Design (``gt-merkle-v2``)
-------------------------
* A record's fields are serialised as canonical JSON (sorted keys, no whitespace, UTF-8) and
  each field becomes one leaf: ``SHA-256(0x00 || name || 0x1f || canonical_json(value))``.
  The ``project_id``, ``sequence`` and ``prev_root_hash`` are leaves, so a record cannot be
  replayed into another project or position.
* Leaves are combined pairwise: ``SHA-256(0x01 || left || right)``. An odd node is promoted
  unchanged (never duplicated), which avoids the duplicate-leaf ambiguity of naive trees.
* ``prev_root_hash`` is the previous record's root (``"genesis"`` for the first), forming a
  chain per project. The *ledger root* is the Merkle root over the ordered record roots.
* A report is bound to the ledger by a ``report.sealed`` record carrying the SHA-256 of the
  exact report bytes.

Honest limits
-------------
Nothing here is an external timestamp or a signature. Someone with database write access who
recomputes every later root can rewrite history, and deleting the *newest* record is only
detectable from a report or header that remembers the earlier head. Reports therefore carry the
record id and ledger root so they can be checked against the live ledger later.

Nothing is invented: when no dataset or intermediate hashes are supplied, the record stores
empty maps and says so; an empty ledger reports ``empty``, never ``verified``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session, sessionmaker

from groundtruth.contracts import CONTRACT_VERSION
from groundtruth.engine import ENGINE_VERSION

logger = logging.getLogger(__name__)

HASH_SCHEME = "gt-merkle-v2"
GENESIS = "genesis"
KIND_ASSESSMENT = "assessment"
KIND_REPORT_SEALED = "report.sealed"
KIND_OBSERVATION_INGESTED = "observation.ingested"
_MAX_APPEND_ATTEMPTS = 12

STATUS_EMPTY = "empty"
STATUS_VERIFIED = "verified"
STATUS_FAILED = "failed"
STATUS_LEGACY = "legacy_unverifiable"


# ---------------------------------------------------------------------------
# Hash primitives
# ---------------------------------------------------------------------------


def get_current_git_commit() -> str:
    """Current Git commit SHA, or ``"unknown"`` — never an invented value."""
    env_sha = os.environ.get("GIT_COMMIT_SHA")
    if env_sha:
        return env_sha
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=2.0,
        )
        return res.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def canonical_json(value: Any) -> bytes:
    """Canonical JSON bytes: sorted keys, compact separators, UTF-8."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def compute_sha256(data: str | bytes | dict[str, Any]) -> str:
    """``sha256:<hex>`` of ``data`` (dicts are canonicalised first)."""
    if isinstance(data, dict):
        raw = canonical_json(data)
    elif isinstance(data, str):
        raw = data.encode("utf-8")
    else:
        raw = data
    return f"sha256:{hashlib.sha256(raw).hexdigest()}"


def _leaf(name: str, value: Any) -> bytes:
    return hashlib.sha256(b"\x00" + name.encode() + b"\x1f" + canonical_json(value)).digest()


def _node(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(b"\x01" + left + right).digest()


def merkle_root(leaves: list[bytes]) -> bytes:
    """Merkle root of ``leaves`` (odd nodes promoted). An empty list has no root."""
    if not leaves:
        raise ValueError("a Merkle tree needs at least one leaf")
    level = list(leaves)
    while len(level) > 1:
        nxt = [_node(level[i], level[i + 1]) for i in range(0, len(level) - 1, 2)]
        if len(level) % 2:
            nxt.append(level[-1])
        level = nxt
    return level[0]


def normalise_timestamp(value: datetime | str) -> str:
    """UTC ISO-8601 with microseconds, the single form that is hashed and stored."""
    dt = datetime.fromisoformat(value) if isinstance(value, str) else value
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


_LEAF_FIELDS: tuple[str, ...] = (
    "project_id",
    "sequence",
    "prev_root_hash",
    "record_kind",
    "timestamp",
    "git_commit_sha",
    "contract_version",
    "engine_version",
    "methodology_version",
    "report_version",
    "boundary_geometry_hash",
    "input_files_hashes",
    "dataset_versions_hashes",
    "analytical_parameters",
    "intermediate_hashes",
    "final_findings",
    "deterministic_reproducible",
)


@dataclass(frozen=True)
class AuditRecord:
    """Immutable audit trail entry."""

    record_id: str
    project_id: str
    timestamp: str
    git_commit_sha: str
    contract_version: str
    engine_version: str
    methodology_version: str
    boundary_geometry_hash: str
    input_files_hashes: dict[str, str]
    dataset_versions_hashes: dict[str, str]
    analytical_parameters: dict[str, Any]
    intermediate_hashes: dict[str, str]
    final_findings: dict[str, Any]
    report_version: str
    merkle_root_hash: str
    deterministic_reproducible: bool
    sequence: int | None = None
    prev_root_hash: str | None = None
    record_kind: str = KIND_ASSESSMENT
    hash_scheme: str | None = HASH_SCHEME

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def recompute_root(self) -> str:
        """Root recomputed from the record's own fields (``sha256:<hex>``)."""
        return _root_for(self.to_dict())


def _root_for(fields: dict[str, Any]) -> str:
    values = dict(fields)
    values["timestamp"] = normalise_timestamp(values["timestamp"])
    leaves = [_leaf(name, values.get(name)) for name in _LEAF_FIELDS]
    return f"sha256:{merkle_root(leaves).hex()}"


def ledger_root(record_roots: list[str]) -> str | None:
    """Merkle root over ordered record roots, or ``None`` for an empty ledger."""
    if not record_roots:
        return None
    leaves = [bytes.fromhex(r.removeprefix("sha256:")) for r in record_roots]
    return f"sha256:{merkle_root(leaves).hex()}"


# ---------------------------------------------------------------------------
# Verification result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LedgerFailure:
    record_id: str | None
    sequence: int | None
    reason: str


@dataclass(frozen=True)
class LedgerVerification:
    """What a verification run actually established."""

    project_id: str
    status: str
    record_count: int
    legacy_record_count: int
    head_sequence: int | None
    head_record_id: str | None
    ledger_root: str | None
    verified_at: str
    failures: list[LedgerFailure] = field(default_factory=list)
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

_ENGINES: dict[str, sa.Engine] = {}
_ENGINES_LOCK = threading.Lock()


def _default_session_factory() -> sessionmaker[Session] | None:
    """Session factory for the configured database, or ``None`` when there is none."""
    try:
        from groundtruth.platform.config import get_settings
        from groundtruth.platform.store.database import create_db_engine, create_session_factory

        url = get_settings().database_url
        if not url:
            return None
        with _ENGINES_LOCK:
            engine = _ENGINES.get(url)
            if engine is None:
                engine = create_db_engine(url)
                _ENGINES[url] = engine
        return create_session_factory(engine)
    except Exception as exc:
        logger.debug("Database not available for the audit ledger: %s", exc)
        return None


def _row_to_record(row: Any) -> AuditRecord:
    return AuditRecord(
        record_id=row.record_id,
        project_id=row.project_id,
        timestamp=normalise_timestamp(row.timestamp),
        git_commit_sha=row.git_commit_sha,
        contract_version=row.contract_version,
        engine_version=row.engine_version,
        methodology_version=row.methodology_version,
        boundary_geometry_hash=row.boundary_geometry_hash,
        input_files_hashes=row.input_files_hashes,
        dataset_versions_hashes=row.dataset_versions_hashes,
        analytical_parameters=row.analytical_parameters,
        intermediate_hashes=row.intermediate_hashes,
        final_findings=row.final_findings,
        report_version=row.report_version,
        merkle_root_hash=row.merkle_root_hash,
        deterministic_reproducible=bool(row.deterministic_reproducible),
        sequence=row.sequence,
        prev_root_hash=row.prev_root_hash,
        record_kind=row.record_kind or KIND_ASSESSMENT,
        hash_scheme=row.hash_scheme,
    )


class AuditLedger:
    """Append-only, hash-chained audit ledger backed by the database when one is configured.

    With no database the ledger lives in memory (tests, local runs) and says nothing about
    durability; callers that need durability must configure ``DATABASE_URL``.
    """

    def __init__(self, session_factory: Callable[[], Session] | None = None) -> None:
        self._explicit_factory = session_factory
        self._memory: dict[str, list[AuditRecord]] = {}
        self._lock = threading.Lock()

    # -- storage helpers ---------------------------------------------------

    def _factory(self) -> Callable[[], Session] | None:
        return self._explicit_factory or _default_session_factory()

    @property
    def durable(self) -> bool:
        return self._factory() is not None

    def _load(self, project_id: str) -> list[AuditRecord]:
        """All records of a project, v2 records ordered by sequence, legacy rows first."""
        factory = self._factory()
        if factory is None:
            return list(self._memory.get(project_id, []))
        from groundtruth.platform.store.models import AuditRecordRow

        with factory() as session:
            rows = (
                session.execute(
                    sa.select(AuditRecordRow)
                    .where(AuditRecordRow.project_id == project_id)
                    .order_by(
                        sa.func.coalesce(AuditRecordRow.sequence, 0).asc(),
                        AuditRecordRow.timestamp.asc(),
                        AuditRecordRow.record_id.asc(),
                    )
                )
                .scalars()
                .all()
            )
            return [_row_to_record(r) for r in rows]

    # -- writing -------------------------------------------------------------

    def _append(
        self,
        *,
        project_id: str,
        record_kind: str,
        boundary_geometry_hash: str,
        input_files_hashes: dict[str, str],
        dataset_versions_hashes: dict[str, str],
        analytical_parameters: dict[str, Any],
        intermediate_hashes: dict[str, str],
        final_findings: dict[str, Any],
        report_version: str,
        methodology_version: str,
        deterministic_reproducible: bool,
        timestamp: str | None,
    ) -> AuditRecord:
        ts = normalise_timestamp(timestamp or datetime.now(UTC))
        git_sha = get_current_git_commit()
        last_error: Exception | None = None
        for _ in range(_MAX_APPEND_ATTEMPTS):
            with self._lock:
                v2 = [r for r in self._load(project_id) if r.hash_scheme == HASH_SCHEME]
                head = v2[-1] if v2 else None
                sequence = (head.sequence or 0) + 1 if head else 1
                prev_root = head.merkle_root_hash if head else GENESIS
                body: dict[str, Any] = {
                    "project_id": project_id,
                    "sequence": sequence,
                    "prev_root_hash": prev_root,
                    "record_kind": record_kind,
                    "timestamp": ts,
                    "git_commit_sha": git_sha,
                    "contract_version": CONTRACT_VERSION,
                    "engine_version": ENGINE_VERSION,
                    "methodology_version": methodology_version,
                    "report_version": report_version,
                    "boundary_geometry_hash": boundary_geometry_hash,
                    "input_files_hashes": input_files_hashes,
                    "dataset_versions_hashes": dataset_versions_hashes,
                    "analytical_parameters": analytical_parameters,
                    "intermediate_hashes": intermediate_hashes,
                    "final_findings": final_findings,
                    "deterministic_reproducible": deterministic_reproducible,
                }
                root = _root_for(body)
                record = AuditRecord(
                    record_id=f"AUDIT-{root.removeprefix('sha256:')[:40]}",
                    merkle_root_hash=root,
                    hash_scheme=HASH_SCHEME,
                    **body,
                )
                try:
                    self._store(record)
                    return record
                except (IntegrityError, OperationalError) as exc:
                    # Another writer took this sequence (or the database was busy): re-read
                    # the head and try again rather than forking the chain.
                    last_error = exc
        raise RuntimeError(
            f"could not append to the audit ledger after {_MAX_APPEND_ATTEMPTS} attempts"
        ) from last_error

    def _store(self, record: AuditRecord) -> None:
        factory = self._factory()
        if factory is None:
            self._memory.setdefault(record.project_id, []).append(record)
            return
        from groundtruth.platform.store.models import AuditRecordRow

        with factory() as session:
            try:
                session.add(
                    AuditRecordRow(
                        record_id=record.record_id,
                        project_id=record.project_id,
                        timestamp=datetime.fromisoformat(record.timestamp.replace("Z", "+00:00")),
                        git_commit_sha=record.git_commit_sha,
                        contract_version=record.contract_version,
                        engine_version=record.engine_version,
                        methodology_version=record.methodology_version,
                        boundary_geometry_hash=record.boundary_geometry_hash,
                        input_files_hashes=record.input_files_hashes,
                        dataset_versions_hashes=record.dataset_versions_hashes,
                        analytical_parameters=record.analytical_parameters,
                        intermediate_hashes=record.intermediate_hashes,
                        final_findings=record.final_findings,
                        report_version=record.report_version,
                        merkle_root_hash=record.merkle_root_hash,
                        deterministic_reproducible=record.deterministic_reproducible,
                        sequence=record.sequence,
                        prev_root_hash=record.prev_root_hash,
                        record_kind=record.record_kind,
                        hash_scheme=record.hash_scheme,
                    )
                )
                session.commit()
            except Exception:
                session.rollback()
                raise

    def record_assessment(
        self,
        project_id: str,
        boundary_geojson: str | dict[str, Any],
        analytical_parameters: dict[str, Any],
        final_findings: dict[str, Any],
        dataset_hashes: dict[str, str] | None = None,
        intermediate_hashes: dict[str, str] | None = None,
        input_files: dict[str, str] | None = None,
        timestamp_override: str | None = None,
        *,
        methodology_version: str = "unspecified",
        deterministic_reproducible: bool = False,
    ) -> AuditRecord:
        """Append an assessment record. Only what the caller supplies is recorded."""
        geom_hash = compute_sha256(boundary_geojson)
        return self._append(
            project_id=project_id,
            record_kind=KIND_ASSESSMENT,
            boundary_geometry_hash=geom_hash,
            input_files_hashes=input_files
            or {
                "boundary_geojson": geom_hash,
                "analytical_parameters": compute_sha256(analytical_parameters),
            },
            dataset_versions_hashes=dataset_hashes or {},
            analytical_parameters=analytical_parameters,
            intermediate_hashes=intermediate_hashes or {},
            final_findings=final_findings,
            report_version="assessment",
            methodology_version=methodology_version,
            deterministic_reproducible=deterministic_reproducible,
            timestamp=timestamp_override,
        )

    def record_report_seal(
        self,
        project_id: str,
        *,
        report_kind: str,
        content: bytes,
        boundary_geometry_hash: str,
        details: dict[str, Any] | None = None,
    ) -> AuditRecord:
        """Bind the exact bytes of a generated report to the ledger."""
        content_hash = compute_sha256(content)
        return self._append(
            project_id=project_id,
            record_kind=KIND_REPORT_SEALED,
            boundary_geometry_hash=boundary_geometry_hash,
            input_files_hashes={report_kind: content_hash},
            dataset_versions_hashes={},
            analytical_parameters={},
            intermediate_hashes={},
            final_findings={
                "report_kind": report_kind,
                "report_sha256": content_hash,
                "report_size_bytes": len(content),
                **(details or {}),
            },
            report_version=report_kind,
            methodology_version="unspecified",
            deterministic_reproducible=False,
            timestamp=None,
        )

    def record_observation_ingest(
        self,
        project_id: str,
        *,
        boundary_geometry_hash: str,
        parameters: dict[str, Any],
        stored_bundles: dict[str, str],
        findings: dict[str, Any],
        code_version: str,
    ) -> AuditRecord:
        """Record what an ingestion fetched: its parameters and the hash of every bundle it stored.

        ``stored_bundles`` maps a bundle name (for example ``ndvi``) to the SHA-256 of the exact
        file written, so the observations a later assessment used can be traced back to this
        record and re-checked against the file on disk.
        """
        return self._append(
            project_id=project_id,
            record_kind=KIND_OBSERVATION_INGESTED,
            boundary_geometry_hash=boundary_geometry_hash,
            input_files_hashes=dict(stored_bundles),
            dataset_versions_hashes={},
            analytical_parameters=parameters,
            intermediate_hashes={},
            final_findings=findings,
            report_version=f"observation-ingestion/{code_version}",
            methodology_version="aoi-zonal-median-mean",
            deterministic_reproducible=False,
            timestamp=None,
        )

    # -- reading -------------------------------------------------------------

    def get_records(self, project_id: str) -> list[AuditRecord]:
        """The project's records, oldest first. An unknown project has none (never invented)."""
        return self._load(project_id)

    def get_record_by_id(self, record_id: str) -> AuditRecord | None:
        factory = self._factory()
        if factory is None:
            for recs in self._memory.values():
                for r in recs:
                    if r.record_id == record_id:
                        return r
            return None
        from groundtruth.platform.store.models import AuditRecordRow

        with factory() as session:
            row = session.get(AuditRecordRow, record_id)
            return _row_to_record(row) if row else None

    # -- verification ----------------------------------------------------------

    def verify_project(self, project_id: str) -> LedgerVerification:
        """Verify every record's root and the chain linking them."""
        now = datetime.now(UTC).isoformat()
        records = self._load(project_id)
        legacy = [r for r in records if r.hash_scheme != HASH_SCHEME]
        chain = [r for r in records if r.hash_scheme == HASH_SCHEME]
        failures: list[LedgerFailure] = []

        expected_prev = GENESIS
        for index, rec in enumerate(chain, start=1):
            if rec.sequence != index:
                failures.append(
                    LedgerFailure(
                        rec.record_id,
                        rec.sequence,
                        f"sequence {rec.sequence} found where {index} was expected "
                        "(a record was removed, inserted or reordered)",
                    )
                )
            if rec.prev_root_hash != expected_prev:
                failures.append(
                    LedgerFailure(
                        rec.record_id,
                        rec.sequence,
                        "chain link broken: previous root does not match the preceding record",
                    )
                )
            recomputed = rec.recompute_root()
            if recomputed != rec.merkle_root_hash:
                failures.append(
                    LedgerFailure(
                        rec.record_id,
                        rec.sequence,
                        "record content does not match its stored Merkle root (modified)",
                    )
                )
            expected_prev = rec.merkle_root_hash

        head = chain[-1] if chain else None
        root = ledger_root([r.merkle_root_hash for r in chain])
        if failures:
            status, message = STATUS_FAILED, "Integrity check FAILED: the ledger was altered."
        elif chain:
            status = STATUS_VERIFIED
            message = (
                f"{len(chain)} record(s) recomputed from stored content; chain intact. "
                "Not externally timestamped or signed."
            )
        elif legacy:
            status = STATUS_LEGACY
            message = (
                f"{len(legacy)} legacy record(s) written before hash chaining; "
                "they cannot be verified."
            )
        else:
            status, message = STATUS_EMPTY, "No audit records exist for this project yet."
        return LedgerVerification(
            project_id=project_id,
            status=status,
            record_count=len(chain),
            legacy_record_count=len(legacy),
            head_sequence=head.sequence if head else None,
            head_record_id=head.record_id if head else None,
            ledger_root=root,
            verified_at=now,
            failures=failures,
            message=message,
        )

    def verify_integrity(self, record_id: str) -> tuple[bool, str]:
        """Check one record against its stored root, and its project's chain."""
        rec = self.get_record_by_id(record_id)
        if rec is None:
            return False, f"Audit record {record_id!r} not found."
        if rec.hash_scheme != HASH_SCHEME:
            return False, "Legacy record: written before hash chaining, cannot be verified."
        if rec.recompute_root() != rec.merkle_root_hash:
            return (
                False,
                "TAMPERING DETECTED: record content does not match its stored Merkle root.",
            )
        result = self.verify_project(rec.project_id)
        if result.status == STATUS_FAILED:
            return False, "TAMPERING DETECTED: the project's ledger chain is broken."
        return True, "Record recomputed from stored content and the project chain is intact."

    def verify_report(self, record_id: str, content: bytes) -> tuple[bool, str]:
        """Check that ``content`` is exactly the report sealed by ``record_id``."""
        rec = self.get_record_by_id(record_id)
        if rec is None:
            return False, "The sealing record was not found in the ledger."
        if rec.record_kind != KIND_REPORT_SEALED:
            return False, "That record does not seal a report."
        ok, message = self.verify_integrity(record_id)
        if not ok:
            return False, message
        if rec.final_findings.get("report_sha256") != compute_sha256(content):
            return False, "The file does not match the report that was sealed."
        return True, "The file is byte-identical to the sealed report and the ledger is intact."

    def verify_reproducibility(self, record_id: str, recomputed_findings: dict[str, Any]) -> bool:
        """Whether a re-run produced identical numerical findings to the recorded ones.

        Only keys present in *both* mappings are compared, and at least one must be.
        """
        rec = self.get_record_by_id(record_id)
        if rec is None:
            return False
        shared = [k for k in rec.final_findings if k in recomputed_findings]
        if not shared:
            return False
        for k in shared:
            a, b = rec.final_findings[k], recomputed_findings[k]
            if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                if abs(a - b) > 1e-6:
                    return False
            elif a != b:
                return False
        return True


_GLOBAL_AUDIT_LEDGER = AuditLedger()


def get_global_audit_ledger() -> AuditLedger:
    """Return the process-wide ledger (database-backed when ``DATABASE_URL`` is set)."""
    return _GLOBAL_AUDIT_LEDGER
