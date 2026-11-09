"""Relational schema for cases, runs, evidence bundles, datasets and jobs.

**Owner: Bhumi.**

The shape follows ``docs/architecture/backend.md``: evidence bundles are stored as
one JSON document (JSONB on PostgreSQL) with a few indexed projection columns for
listing. Fully normalising a bundle would be premature; the object is already
shaped for a document column (ADR-004).

Two rules shape the schema:

* **Bundles are immutable.** A re-run is a new ``run_id``, never an update. The
  migration installs a database trigger so this holds even for code that bypasses
  this module; a convention alone only makes a mutation unlikely.
* **A bundle carries the contract version it was written under**, so a bundle
  stored today stays readable after a minor contract bump (see :func:`load_bundle`).

This module defines the schema and the read helpers that check a stored record's
contract version. Saving and retrieving results is the evidence store
(:mod:`groundtruth.platform.store.sql`, behind :mod:`groundtruth.platform.store.interface`).

Timestamps are timezone-aware. SQLite does not keep the offset and returns naive
values; the bundle document is unaffected because it stores its timestamps as ISO
strings inside the JSON.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from groundtruth.contracts.evidence import EvidenceBundle
from groundtruth.contracts.result import AnalysisStatus
from groundtruth.contracts.version import (
    CONTRACT_VERSION,
    MIN_SUPPORTED_CONTRACT_VERSION,
    is_compatible,
    parse_version,
)
from groundtruth.platform.store.interface import IncompatibleBundleError

# Registers the append-only guard for audit_events whenever the schema is imported.
import groundtruth.platform.audit  # noqa: F401  isort:skip

# Explicit constraint names make migrations reproducible and give Alembic stable
# names to drop on downgrade. SQLite in particular cannot drop an unnamed constraint.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

DATA_MODES: tuple[str, ...] = ("observed", "simulated")
"""Mirrors ``AnalysisRequest.data_mode``. Owned by the platform (R7)."""

CASE_STATUSES: tuple[str, ...] = ("scaffolded", "data-wired", "analysed")
"""Mirrors ``CaseDefinition.status``. Only a reviewed real run may set ``analysed``."""

NOT_ASSESSED = "not_assessed"
"""Projected verdict label for a bundle that carries no verdict."""

# ``none_as_null`` stores Python ``None`` as SQL NULL rather than the JSON value
# ``null``, so "no error" is queryable with ``IS NULL`` on both dialects.
JsonDocument = sa.JSON(none_as_null=True).with_variant(JSONB(none_as_null=True), "postgresql")


class Base(DeclarativeBase):
    """Declarative base carrying the shared naming convention."""

    metadata = sa.MetaData(naming_convention=NAMING_CONVENTION)


def _in_list(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"


class CaseRow(Base):
    """A project definition. Today these live in YAML; the table is the synced copy."""

    __tablename__ = "cases"
    __table_args__ = (sa.CheckConstraint(_in_list("status", CASE_STATUSES), name="status_valid"),)

    case_id: Mapped[str] = mapped_column(sa.String(100), primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(200))
    country: Mapped[str] = mapped_column(sa.String(100))
    indicator: Mapped[str] = mapped_column(sa.String(40))
    status: Mapped[str] = mapped_column(sa.String(20))
    definition: Mapped[dict[str, Any]] = mapped_column(JsonDocument)
    """The case document. Must not carry ``known_reference`` into anything the engine sees."""
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )


class AnalysisRunRow(Base):
    """One attempt to analyse one case. Also the single source of job status.

    ``status`` is the platform lifecycle (:class:`AnalysisStatus`); ``engine_status``
    is what the engine found. A run can be ``succeeded`` with ``engine_status`` of
    ``refused``; that is a legitimate outcome, so the structured ``error`` lives here
    and not on the bundle row (a refused run has no bundle).

    ``dataset_refs`` is a snapshot of the pinned datasets the run used. The
    ``datasets`` table is the registry; the snapshot is what makes a re-run months
    later use the same imagery.
    """

    __tablename__ = "analysis_runs"
    __table_args__ = (
        sa.CheckConstraint(
            _in_list("status", tuple(s.value for s in AnalysisStatus)), name="status_valid"
        ),
        sa.CheckConstraint(_in_list("data_mode", DATA_MODES), name="data_mode_valid"),
        # R7: the simulated flag cannot disagree with the declared data mode. A
        # result that would break this is refused at write time rather than served.
        sa.CheckConstraint(
            "is_simulated = (data_mode = 'simulated')", name="simulated_flag_matches_data_mode"
        ),
        # Target of the composite foreign key from evidence_bundles.
        sa.UniqueConstraint("run_id", "case_id"),
        # Keyset pagination (issue #35) orders by (created_at DESC, run_id DESC), so each
        # filter's index ends in run_id and a page is a range scan with no sort.
        sa.Index("ix_analysis_runs_case_id_created_at_run_id", "case_id", "created_at", "run_id"),
        sa.Index("ix_analysis_runs_status_created_at_run_id", "status", "created_at", "run_id"),
        sa.Index(
            "ix_analysis_runs_engine_version_created_at_run_id",
            "engine_version",
            "created_at",
            "run_id",
        ),
        sa.Index("ix_analysis_runs_created_at_run_id", "created_at", "run_id"),
        sa.Index("ix_analysis_runs_spec_hash", "spec_hash"),
    )

    run_id: Mapped[str] = mapped_column(sa.String(32), primary_key=True)
    case_id: Mapped[str] = mapped_column(sa.ForeignKey("cases.case_id"))
    spec_hash: Mapped[str] = mapped_column(sa.String(64))
    status: Mapped[str] = mapped_column(sa.String(16))
    engine_status: Mapped[str | None] = mapped_column(sa.String(16))
    error_code: Mapped[str | None] = mapped_column(sa.String(40))
    error: Mapped[dict[str, Any] | None] = mapped_column(JsonDocument)
    verdict_label: Mapped[str | None] = mapped_column(sa.String(40))
    data_mode: Mapped[str] = mapped_column(sa.String(16))
    is_simulated: Mapped[bool] = mapped_column(sa.Boolean)
    seed: Mapped[int] = mapped_column(sa.BigInteger)
    engine_version: Mapped[str | None] = mapped_column(sa.String(40))
    engine_git_sha: Mapped[str | None] = mapped_column(sa.String(64))
    engine_contract_version: Mapped[str | None] = mapped_column(sa.String(20))
    """Contract version the engine build targets (``EngineRef.contract_version``).

    Distinct from ``contract_version``, which is the version the result was stamped
    with. Added in revision 0002 so a stored result reloads exactly.
    """
    contract_version: Mapped[str] = mapped_column(sa.String(20))
    dataset_refs: Mapped[list[dict[str, Any]]] = mapped_column(JsonDocument)
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JsonDocument)
    request: Mapped[dict[str, Any] | None] = mapped_column(JsonDocument)
    """The full ``AnalysisRequest`` behind this run (revision 0003).

    Stored with the run, not the job, because it is the run's specification: a queued
    run executes exactly this, even after a restart or a change to the case file, and
    monitoring replays it later (ADR-006). ``None`` for a result saved without it.
    """
    requested_by: Mapped[str | None] = mapped_column(sa.String(100))
    project_id: Mapped[str | None] = mapped_column(sa.ForeignKey("projects.id"))
    """The tenant project this run belongs to (revision 0007). ``None`` for legacy runs."""
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class EvidenceBundleRow(Base):
    """The immutable evidence bundle for one completed run.

    ``run_id`` is the primary key: a run has at most one bundle, and a re-run is a
    new run with its own bundle. The projection columns exist so listings never
    have to open the document. ``case_id`` is tied to the run by a composite foreign
    key, so the projection cannot disagree with the run it belongs to.
    """

    __tablename__ = "evidence_bundles"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["run_id", "case_id"], ["analysis_runs.run_id", "analysis_runs.case_id"]
        ),
        sa.CheckConstraint("item_count >= 0", name="item_count_non_negative"),
        sa.Index("ix_evidence_bundles_case_id_created_at", "case_id", "created_at"),
        sa.Index("ix_evidence_bundles_verdict_label_created_at", "verdict_label", "created_at"),
        sa.Index("ix_evidence_bundles_created_at", "created_at"),
    )

    run_id: Mapped[str] = mapped_column(sa.String(32), primary_key=True)
    case_id: Mapped[str] = mapped_column(sa.String(100))
    contract_version: Mapped[str] = mapped_column(sa.String(20))
    bundle: Mapped[dict[str, Any]] = mapped_column(JsonDocument)
    verdict_label: Mapped[str] = mapped_column(sa.String(40))
    item_count: Mapped[int] = mapped_column(sa.Integer)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )


class DatasetRow(Base):
    """A pinned reference to an external dataset, with its retrieval metadata."""

    __tablename__ = "datasets"

    dataset_id: Mapped[str] = mapped_column(sa.String(100), primary_key=True)
    version: Mapped[str] = mapped_column(sa.String(100), primary_key=True)
    provider: Mapped[str] = mapped_column(sa.String(100), primary_key=True)
    asset: Mapped[str | None] = mapped_column(sa.String(500))
    source_uri: Mapped[str | None] = mapped_column(sa.String(1000))
    retrieved_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    is_synthetic: Mapped[bool] = mapped_column(sa.Boolean)
    retrieval_metadata: Mapped[dict[str, Any] | None] = mapped_column(JsonDocument)
    registered_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )


class JobRow(Base):
    """Queue mechanics for one run: attempts, lease, heartbeat and cancellation.

    Deliberately carries no status of its own. ``analysis_runs.status`` is the one
    source of truth, so the job and the run cannot disagree about whether work is
    queued or running. A worker finds work by joining on ``run_id``.
    """

    __tablename__ = "jobs"
    __table_args__ = (
        sa.CheckConstraint("attempts >= 0", name="attempts_non_negative"),
        sa.CheckConstraint("max_attempts >= 1", name="max_attempts_positive"),
        sa.Index("ix_jobs_available_at", "available_at"),
    )

    run_id: Mapped[str] = mapped_column(sa.ForeignKey("analysis_runs.run_id"), primary_key=True)
    project_id: Mapped[str | None] = mapped_column(sa.ForeignKey("projects.id"))
    """Denormalised from the run (revision 0007) so a worker can scope work by project."""
    attempts: Mapped[int] = mapped_column(sa.Integer, server_default="0")
    max_attempts: Mapped[int] = mapped_column(sa.Integer, server_default="3")
    available_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    locked_by: Mapped[str | None] = mapped_column(sa.String(100))
    stage: Mapped[str | None] = mapped_column(sa.String(20))
    """The stage the job is in now: claim, data, engine or record (revision 0005)."""
    stage_log: Mapped[dict[str, str] | None] = mapped_column(JsonDocument)
    """When each stage began, as ``{stage: iso time}``. A stage ends when the next begins."""
    heartbeat_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    """When the current claim lapses unless renewed (revision 0003).

    Stored rather than computed from a configured lease length, so every worker
    agrees on whether a job is abandoned, however each one is configured.
    """
    cancel_requested_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    last_error: Mapped[dict[str, Any] | None] = mapped_column(JsonDocument)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )


def check_readable(
    produced_under: str, run_id: str, *, what: str, consumer_version: str = CONTRACT_VERSION
) -> None:
    """Refuse a stored record written under a contract this consumer cannot read.

    Shared by bundles and run rows. A refused run has no bundle, so its own version
    must be checked too. The check happens before validation on purpose: a record
    from a newer minor or a different major may still *parse* while meaning
    something different, and quietly rendering it would show a number under the
    wrong rules. Refusing is the safe failure (R5); a major bump ships with a
    migration for stored bundles.

    Raises:
        IncompatibleBundleError: if ``produced_under`` is older than the supported
            floor, or not readable by ``consumer_version``.
    """
    too_old = parse_version(produced_under) < parse_version(MIN_SUPPORTED_CONTRACT_VERSION)
    if too_old or not is_compatible(produced_under, consumer_version):
        raise IncompatibleBundleError(
            f"{what} for run {run_id!r} was written under contract {produced_under}, "
            f"which contract {consumer_version} cannot read"
        )


def load_bundle(
    row: EvidenceBundleRow, *, consumer_version: str = CONTRACT_VERSION
) -> EvidenceBundle:
    """Rebuild the :class:`EvidenceBundle` stored in ``row``.

    Args:
        row: A stored bundle.
        consumer_version: Contract version of the code doing the reading. Defaults
            to the running contract; tests pass a later one to simulate a bump.

    Raises:
        IncompatibleBundleError: if the bundle was written under a version this
            consumer cannot read.
    """
    check_readable(
        row.contract_version, row.run_id, what="bundle", consumer_version=consumer_version
    )
    return EvidenceBundle.model_validate(row.bundle)


USER_ROLES: tuple[str, ...] = ("user", "dev", "admin")
"""Account roles, lowest to highest. See ``docs/security/auth.md``."""


class UserRow(Base):
    """An account. ``password_hash`` is a salted scrypt string, never the password."""

    __tablename__ = "users"
    __table_args__ = (
        sa.CheckConstraint(_in_list("role", USER_ROLES), name="role_valid"),
        sa.UniqueConstraint("email"),
    )

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True)
    email: Mapped[str] = mapped_column(sa.String(254))
    """Stored lowercased."""
    password_hash: Mapped[str] = mapped_column(sa.String(300))
    role: Mapped[str] = mapped_column(sa.String(16))
    is_active: Mapped[bool] = mapped_column(sa.Boolean)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class SessionRow(Base):
    """A sign-in. Only the SHA-256 of the cookie token is stored."""

    __tablename__ = "sessions"
    __table_args__ = (sa.UniqueConstraint("token_hash"), sa.Index("ix_sessions_user_id", "user_id"))

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(sa.ForeignKey("users.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(sa.String(64))
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    user_agent: Mapped[str | None] = mapped_column(sa.String(300))
    active_organization_id: Mapped[str | None] = mapped_column(
        sa.ForeignKey("organizations.id", ondelete="SET NULL")
    )
    """The organization this sign-in is acting for (revision 0007)."""


ORG_TYPES: tuple[str, ...] = ("ngo", "funder", "auditor", "government", "reference")
"""Organization kinds. ``reference`` is the system org that owns imported cases."""

MEMBER_ROLES: tuple[str, ...] = ("owner", "admin", "member", "viewer")
"""Roles inside one organization, highest to lowest."""

GRANT_LEVELS: tuple[str, ...] = ("view", "audit", "contribute")
"""What a project owner lets another organization do with a project."""

AUDIT_OUTCOMES: tuple[str, ...] = ("success", "denied", "error")


class OrganizationRow(Base):
    """A tenant: an NGO, funder, auditor, government body or the reference org."""

    __tablename__ = "organizations"
    __table_args__ = (
        sa.CheckConstraint(_in_list("type", ORG_TYPES), name="type_valid"),
        sa.UniqueConstraint("slug"),
    )

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True)
    slug: Mapped[str] = mapped_column(sa.String(100))
    name: Mapped[str] = mapped_column(sa.String(200))
    type: Mapped[str] = mapped_column(sa.String(16))
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))


class MembershipRow(Base):
    """A user's role inside one organization."""

    __tablename__ = "memberships"
    __table_args__ = (
        sa.CheckConstraint(_in_list("role", MEMBER_ROLES), name="role_valid"),
        sa.UniqueConstraint("user_id", "organization_id"),
        sa.Index("ix_memberships_organization_id", "organization_id"),
    )

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(sa.ForeignKey("users.id", ondelete="CASCADE"))
    organization_id: Mapped[str] = mapped_column(
        sa.ForeignKey("organizations.id", ondelete="CASCADE")
    )
    role: Mapped[str] = mapped_column(sa.String(16))
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))


class ProjectRow(Base):
    """A project owned by one organization. ``case_id`` links it to the engine's case."""

    __tablename__ = "projects"
    __table_args__ = (
        sa.CheckConstraint(_in_list("data_mode", DATA_MODES), name="data_mode_valid"),
        sa.UniqueConstraint("slug"),
        sa.UniqueConstraint("case_id"),
        sa.Index("ix_projects_organization_id", "organization_id"),
    )

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True)
    slug: Mapped[str] = mapped_column(sa.String(100))
    organization_id: Mapped[str] = mapped_column(
        sa.ForeignKey("organizations.id", ondelete="CASCADE")
    )
    case_id: Mapped[str | None] = mapped_column(sa.ForeignKey("cases.case_id"))
    name: Mapped[str] = mapped_column(sa.String(200))
    country: Mapped[str] = mapped_column(sa.String(100))
    ecosystem: Mapped[str] = mapped_column(sa.String(100))
    intervention: Mapped[str] = mapped_column(sa.String(100))
    treatment_start_year: Mapped[int] = mapped_column(sa.Integer)
    boundary_path: Mapped[str | None] = mapped_column(sa.String(500))
    boundary_sha256: Mapped[str | None] = mapped_column(sa.String(64))
    data_mode: Mapped[str] = mapped_column(sa.String(16))
    reported_funding_amount: Mapped[float | None] = mapped_column(sa.Numeric(18, 2))
    """Reported by the owner; shown as such, never computed."""
    reported_funding_currency: Mapped[str | None] = mapped_column(sa.String(3))
    created_by: Mapped[str | None] = mapped_column(sa.ForeignKey("users.id", ondelete="SET NULL"))
    """``None`` for projects imported from YAML by the seed, which have no human creator."""
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))


class ProjectGrantRow(Base):
    """Access an owner gives another organization to one project."""

    __tablename__ = "project_grants"
    __table_args__ = (
        sa.CheckConstraint(_in_list("level", GRANT_LEVELS), name="level_valid"),
        sa.UniqueConstraint("project_id", "grantee_organization_id"),
        sa.Index("ix_project_grants_grantee_organization_id", "grantee_organization_id"),
    )

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(sa.ForeignKey("projects.id", ondelete="CASCADE"))
    grantee_organization_id: Mapped[str] = mapped_column(
        sa.ForeignKey("organizations.id", ondelete="CASCADE")
    )
    level: Mapped[str] = mapped_column(sa.String(16))
    granted_by: Mapped[str | None] = mapped_column(sa.ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class AuditEventRow(Base):
    """One security-relevant event. Append-only: no code path updates or deletes it.

    Actor and organization are plain strings rather than foreign keys, so deleting a
    user or organization never rewrites or blocks the history of what they did.
    """

    __tablename__ = "audit_events"
    __table_args__ = (
        sa.CheckConstraint(_in_list("outcome", AUDIT_OUTCOMES), name="outcome_valid"),
        sa.Index("ix_audit_events_occurred_at", "occurred_at"),
        sa.Index("ix_audit_events_organization_id_occurred_at", "organization_id", "occurred_at"),
    )

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    actor_user_id: Mapped[str | None] = mapped_column(sa.String(36))
    organization_id: Mapped[str | None] = mapped_column(sa.String(36))
    action: Mapped[str] = mapped_column(sa.String(100))
    resource_type: Mapped[str] = mapped_column(sa.String(50))
    resource_id: Mapped[str | None] = mapped_column(sa.String(100))
    outcome: Mapped[str] = mapped_column(sa.String(16))
    ip: Mapped[str | None] = mapped_column(sa.String(64))
    user_agent: Mapped[str | None] = mapped_column(sa.String(300))
    details: Mapped[dict[str, Any]] = mapped_column(JsonDocument)


class AuditRecordRow(Base):
    """Cryptographic audit record for a scientific assessment.

    Append-only and tamper-evident: binds input geometry, parameters, commit SHA,
    intermediate hashes, and final findings into a Merkle root hash.
    """

    __tablename__ = "audit_records"
    __table_args__ = (
        sa.Index("ix_audit_records_project_id", "project_id"),
        sa.Index("ix_audit_records_timestamp", "timestamp"),
        sa.Index("ix_audit_records_merkle_root_hash", "merkle_root_hash"),
        sa.Index("uq_audit_records_project_sequence", "project_id", "sequence", unique=True),
    )

    record_id: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    git_commit_sha: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    contract_version: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    engine_version: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    methodology_version: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    boundary_geometry_hash: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    input_files_hashes: Mapped[dict[str, str]] = mapped_column(JsonDocument, nullable=False)
    dataset_versions_hashes: Mapped[dict[str, str]] = mapped_column(JsonDocument, nullable=False)
    analytical_parameters: Mapped[dict[str, Any]] = mapped_column(JsonDocument, nullable=False)
    intermediate_hashes: Mapped[dict[str, str]] = mapped_column(JsonDocument, nullable=False)
    final_findings: Mapped[dict[str, Any]] = mapped_column(JsonDocument, nullable=False)
    report_version: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    merkle_root_hash: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    deterministic_reproducible: Mapped[bool] = mapped_column(
        sa.Boolean, default=False, nullable=False
    )
    # Hash-chain columns (revision 0009). NULL ``hash_scheme`` marks a legacy row written
    # before the chain existed; such rows are reported as unverifiable, never as verified.
    sequence: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    prev_root_hash: Mapped[str | None] = mapped_column(sa.String(128), nullable=True)
    record_kind: Mapped[str] = mapped_column(
        sa.String(32), default="assessment", server_default="assessment", nullable=False
    )
    hash_scheme: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)


DOCUMENT_STATUSES: tuple[str, ...] = (
    "uploaded",
    "text_extracted",
    "extraction_unsupported",
    "extraction_failed",
)


INGESTION_STATUSES: tuple[str, ...] = (
    "queued",
    "running",
    "succeeded",
    "partial",
    "failed",
    "cancelled",
)


class ProjectClaimRow(Base):
    """A claim a person chose to add to a project's verification (revision 0012).

    A row exists only because a user explicitly promoted an extracted statement (or typed a claim);
    nothing is ever promoted automatically. ``original_*`` preserve exactly what the extractor read
    and are never changed; the unprefixed fields are what the user confirms or corrects, and what
    is matched against evidence. ``withdrawn_at`` is a soft delete: the row and its history stay.
    """

    __tablename__ = "project_claims"
    __table_args__ = (sa.Index("ix_project_claims_project_id", "project_id"),)

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(sa.ForeignKey("projects.id", ondelete="CASCADE"))
    source_document_id: Mapped[str | None] = mapped_column(
        sa.ForeignKey("project_documents.id", ondelete="SET NULL")
    )
    source_document_name: Mapped[str | None] = mapped_column(sa.String(255))
    source_document_sha256: Mapped[str | None] = mapped_column(sa.String(64))
    source_start: Mapped[int | None] = mapped_column(sa.Integer)
    source_end: Mapped[int | None] = mapped_column(sa.Integer)
    original_text: Mapped[str] = mapped_column(sa.Text)
    original_kind: Mapped[str | None] = mapped_column(sa.String(48))
    original_value: Mapped[float | None] = mapped_column(sa.Float)
    original_unit: Mapped[str | None] = mapped_column(sa.String(40))
    original_period: Mapped[str | None] = mapped_column(sa.String(60))
    statement_text: Mapped[str] = mapped_column(sa.String(1000))
    kind: Mapped[str] = mapped_column(sa.String(48))
    claimed_value: Mapped[float | None] = mapped_column(sa.Float)
    claimed_unit: Mapped[str | None] = mapped_column(sa.String(40))
    claimed_period: Mapped[str | None] = mapped_column(sa.String(60))
    created_by: Mapped[str | None] = mapped_column(sa.ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    updated_by: Mapped[str | None] = mapped_column(sa.ForeignKey("users.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    withdrawn_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class ObservationIngestionRow(Base):
    """A request to ingest satellite observations for one project's boundary (revision 0011).

    ``queued`` -> ``running`` -> ``succeeded`` | ``partial`` | ``failed``. ``partial`` means some
    requested years have no usable value (cloud cover, missing tiles, coverage below the
    threshold); it is never reported as complete. ``result`` holds only what the pipeline
    measured: per-year scenes, tiles, coverage and the fingerprints of the stored bundles.
    """

    __tablename__ = "observation_ingestions"
    __table_args__ = (
        sa.CheckConstraint(_in_list("status", INGESTION_STATUSES), name="status_valid"),
        sa.Index("ix_observation_ingestions_project_created", "project_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(sa.ForeignKey("projects.id", ondelete="CASCADE"))
    requested_by: Mapped[str | None] = mapped_column(sa.ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(sa.String(16))
    params: Mapped[dict[str, Any]] = mapped_column(JsonDocument)
    status_detail: Mapped[str | None] = mapped_column(sa.String(1000))
    error_code: Mapped[str | None] = mapped_column(sa.String(48))
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    worker_id: Mapped[str | None] = mapped_column(sa.String(100))
    result: Mapped[dict[str, Any] | None] = mapped_column(JsonDocument, nullable=True)
    ledger_record_id: Mapped[str | None] = mapped_column(sa.String(64))


class ProjectDocumentRow(Base):
    """A document an organization uploaded to one of its projects (revision 0010).

    ``status`` is honest about processing: ``uploaded`` means stored and hashed, nothing more.
    Nothing here is ever "verified"; the claim count is a count of text candidates only.
    """

    __tablename__ = "project_documents"
    __table_args__ = (
        sa.CheckConstraint(_in_list("status", DOCUMENT_STATUSES), name="status_valid"),
        sa.Index("ix_project_documents_project_id", "project_id"),
    )

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(sa.ForeignKey("projects.id", ondelete="CASCADE"))
    original_filename: Mapped[str] = mapped_column(sa.String(255))
    """Sanitised display name; never used as a filesystem path."""
    content_type: Mapped[str] = mapped_column(sa.String(100))
    size_bytes: Mapped[int] = mapped_column(sa.Integer)
    sha256: Mapped[str] = mapped_column(sa.String(64))
    storage_key: Mapped[str] = mapped_column(sa.String(300))
    uploaded_by: Mapped[str | None] = mapped_column(sa.ForeignKey("users.id", ondelete="SET NULL"))
    uploaded_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    status: Mapped[str] = mapped_column(sa.String(32))
    status_detail: Mapped[str | None] = mapped_column(sa.String(500))
    extracted_text_chars: Mapped[int | None] = mapped_column(sa.Integer)
    extracted_claims_count: Mapped[int | None] = mapped_column(sa.Integer)
    deleted_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    """Soft delete: the row and its audit trail stay; the stored bytes are removed."""
