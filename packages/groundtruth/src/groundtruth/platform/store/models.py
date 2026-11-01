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
        sa.Index("ix_analysis_runs_case_id_created_at", "case_id", "created_at"),
        sa.Index("ix_analysis_runs_status_created_at", "status", "created_at"),
        sa.Index("ix_analysis_runs_spec_hash", "spec_hash"),
        sa.Index("ix_analysis_runs_created_at", "created_at"),
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
    requested_by: Mapped[str | None] = mapped_column(sa.String(100))
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
    attempts: Mapped[int] = mapped_column(sa.Integer, server_default="0")
    max_attempts: Mapped[int] = mapped_column(sa.Integer, server_default="3")
    available_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    locked_by: Mapped[str | None] = mapped_column(sa.String(100))
    heartbeat_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
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
