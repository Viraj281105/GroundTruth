"""The evidence store on a SQL database.

**Owner: Bhumi.**

Implements :class:`~groundtruth.platform.store.interface.EvidenceStore` over the
schema from issue #14. The evidence bundle is the irreplaceable artefact here: its
provenance cannot be rebuilt if the source data later changes, so the rules are
strict. A run is written once and atomically, a stored result reloads exactly, and
anything the code cannot read faithfully is refused rather than approximated (R5).

``save_result`` writes a finished result as a new run. A queued run that finishes later
is completed by the job layer (issue #24) through :func:`record_result`, so both paths
write a result the same way.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session, sessionmaker

from groundtruth.contracts.identifiers import DatasetRef, EngineRef
from groundtruth.contracts.result import (
    AnalysisError,
    AnalysisResult,
    AnalysisStatus,
    EngineStatus,
    RunMetrics,
)
from groundtruth.contracts.version import CONTRACT_VERSION
from groundtruth.platform.cases.registry import CaseDefinition
from groundtruth.platform.store.interface import (
    MAX_FAILURE_REASON,
    DataMode,
    DuplicateRunError,
    RunCursor,
    RunFilter,
    RunPage,
    RunSummary,
    StoreError,
    UnknownCaseError,
)
from groundtruth.platform.store.models import (
    NOT_ASSESSED,
    AnalysisRunRow,
    CaseRow,
    EvidenceBundleRow,
    JobRow,
    check_readable,
    load_bundle,
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    """A stored timestamp as an aware UTC datetime.

    SQLite returns naive values. Every value this store writes is UTC, so a naive one
    read back is UTC too.
    """
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _parse_timestamp(value: str | None, field: str) -> datetime | None:
    """Parse an engine timestamp for storage.

    The contract types these as free strings; the engine always writes aware ISO-8601
    (``datetime.now(UTC).isoformat()``). A value that is not that is refused, not
    guessed at: a naive timestamp has no defined instant.
    """
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise StoreError(f"{field} {value!r} is not an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise StoreError(f"{field} {value!r} has no timezone, so it names no instant")
    return parsed.astimezone(UTC)


def _format_timestamp(value: datetime | None) -> str | None:
    """Inverse of :func:`_parse_timestamp`; reproduces the engine's own string."""
    return None if value is None else _as_utc(value).isoformat()


def _case_definition(case: CaseDefinition) -> dict[str, Any]:
    """The case as stored. ``known_reference`` is deliberately left out.

    It is a published third-party finding kept for post-hoc validation. It has no
    place in the run archive, and keeping it out of anything the store holds removes
    one way for it to drift toward the engine, which must never see it.
    """
    return {
        "case_id": case.case_id,
        "claim": case.claim.model_dump(mode="json"),
        "indicator": case.indicator.value,
        "window": case.window.model_dump(mode="json"),
        "donor_search_region": case.donor_search_region.strip(),
        "donor_pool_size": case.donor_pool_size,
        "excluded_donor_ids": list(case.excluded_donor_ids),
        "covariates": list(case.covariates),
        "ecosystem": case.ecosystem,
        "notes": case.notes,
        "status": case.status,
    }


def _run_status(result: AnalysisResult) -> AnalysisStatus:
    """Map the engine's outcome to the platform lifecycle (ADR-008).

    A refusal is a legitimate result, so the job *succeeded*. Only an engine error,
    where the engine could not run, is a failed job.
    """
    return (
        AnalysisStatus.FAILED if result.status is EngineStatus.ERROR else AnalysisStatus.SUCCEEDED
    )


def _apply_result(run: AnalysisRunRow, result: AnalysisResult) -> None:
    """Copy a finished result onto a run row. Identity columns are left alone."""
    started_at = _parse_timestamp(result.started_at, "started_at")
    finished_at = _parse_timestamp(result.finished_at, "finished_at")
    run.status = _run_status(result).value
    run.engine_status = result.status.value
    run.error_code = result.error.code.value if result.error else None
    run.error = result.error.model_dump(mode="json") if result.error else None
    run.verdict_label = result.verdict_label
    run.is_simulated = result.is_simulated
    run.seed = result.seed
    run.engine_version = result.engine.engine_version
    run.engine_git_sha = result.engine.git_sha
    run.engine_contract_version = result.engine.contract_version
    run.contract_version = result.contract_version
    run.dataset_refs = [d.model_dump(mode="json") for d in result.datasets]
    run.metrics = result.metrics.model_dump(mode="json")
    run.started_at = started_at
    run.finished_at = finished_at


def record_result(
    session: Session, run: AnalysisRunRow, result: AnalysisResult, *, written_at: datetime
) -> None:
    """Write a finished result onto ``run`` and add its bundle, in the caller's transaction.

    Shared by :meth:`SqlEvidenceStore.save_result` (a new row) and the job layer (a
    queued row whose engine run has finished). The caller owns the transaction, so the
    result lands atomically with whatever else it guards; for a job, the lease check.

    Raises:
        StoreError: if the result does not belong to this run. Writing another
            specification's numbers under this run's id would mislabel them.
    """
    expected = (run.run_id, run.case_id, run.spec_hash, run.data_mode)
    actual = (result.run_id, result.case_id, result.spec_hash, result.data_mode)
    if expected != actual:
        raise StoreError(
            f"result does not belong to run {run.run_id!r}: expected (run_id, case_id, "
            f"spec_hash, data_mode) {expected}, got {actual}"
        )
    _apply_result(run, result)
    # No relationship() links these, so SQLAlchemy would not order the inserts: the
    # run row must be written before its bundle references it.
    session.flush()
    if result.bundle is not None:
        session.add(_bundle_row(result, written_at))


def _bundle_row(result: AnalysisResult, created_at: datetime) -> EvidenceBundleRow:
    bundle = result.bundle
    assert bundle is not None  # callers check; the contract guarantees it when completed
    return EvidenceBundleRow(
        run_id=result.run_id,
        case_id=result.case_id,
        contract_version=result.contract_version,
        bundle=bundle.model_dump(mode="json"),
        verdict_label=bundle.verdict.label.value if bundle.verdict else NOT_ASSESSED,
        item_count=len(bundle),
        created_at=created_at,
    )


def failure_reason_for(run: AnalysisRunRow, last_error: dict[str, Any] | None) -> str | None:
    """Why a run failed, when nothing else explains it.

    A run that failed in the engine carries its stored ``error``; that is the
    explanation, so no reason is added. Otherwise the job's last error says why (an
    unusable request, a result that could not be stored, a bug). It is cut short
    because it can carry exception text.
    """
    if run.status != "failed" or run.error is not None or not last_error:
        return None
    reason = last_error.get("reason")
    if not isinstance(reason, str) or not reason:
        return None
    return reason[:MAX_FAILURE_REASON]


def _summary(run: AnalysisRunRow, last_error: dict[str, Any] | None = None) -> RunSummary:
    return RunSummary(
        run_id=run.run_id,
        case_id=run.case_id,
        spec_hash=run.spec_hash,
        status=run.status,
        engine_status=run.engine_status,
        error_code=run.error_code,
        verdict_label=run.verdict_label,
        data_mode=run.data_mode,
        is_simulated=run.is_simulated,
        engine_version=run.engine_version,
        contract_version=run.contract_version,
        created_at=_as_utc(run.created_at),
        project_id=run.project_id,
        failure_reason=failure_reason_for(run, last_error),
    )


def _with_jobs() -> sa.Select[tuple[AnalysisRunRow, dict[str, Any] | None]]:
    """Runs with their job's last error, if they have a job (saved results have none)."""
    return sa.select(AnalysisRunRow, JobRow.last_error).outerjoin(
        JobRow, JobRow.run_id == AnalysisRunRow.run_id
    )


class SqlEvidenceStore:
    """Evidence store backed by any database SQLAlchemy supports.

    Args:
        session_factory: Builds sessions on the target database. See
            :func:`groundtruth.platform.store.database.create_session_factory`.
        clock: Supplies the write time. ``created_at`` is set here, with microsecond
            precision, rather than by the database: SQLite's clock has one-second
            resolution, which would tie nearly every pair of quick re-runs. Tests
            inject a fixed clock to force ties.
        consumer_version: Contract version of the code reading. Defaults to the
            running contract; tests pass a later one to simulate a bump.
    """

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        clock: Callable[[], datetime] = _utc_now,
        consumer_version: str = CONTRACT_VERSION,
    ) -> None:
        self._sessions = session_factory
        self._clock = clock
        self._consumer_version = consumer_version

    # --- writing ---------------------------------------------------------------

    def upsert_case(self, case: CaseDefinition) -> None:
        """Create or update the stored copy of a case definition.

        Cases are mutable (the YAML changes), unlike runs. This only mirrors the
        file: it does not decide a case's status, and in particular it never promotes
        a case to ``analysed``.
        """
        definition = _case_definition(case)
        with self._sessions.begin() as session:
            row = session.get(CaseRow, case.case_id)
            if row is None:
                row = CaseRow(case_id=case.case_id)
                session.add(row)
            row.name = case.claim.name
            row.country = case.claim.country
            row.indicator = case.indicator.value
            row.status = case.status
            row.definition = definition

    def save_result(self, result: AnalysisResult, *, requested_by: str | None = None) -> None:
        """Store a finished result atomically: the run row and its bundle together.

        Both rows share one transaction, so there is never a completed run without
        its bundle. A duplicate ``run_id`` is rejected up front and, for two writers
        racing, by the primary key.
        """
        created_at = self._clock()
        try:
            with self._sessions.begin() as session:
                if session.get(AnalysisRunRow, result.run_id) is not None:
                    raise DuplicateRunError(f"run {result.run_id!r} is already stored")
                if session.get(CaseRow, result.case_id) is None:
                    raise UnknownCaseError(
                        f"case {result.case_id!r} is not stored; call upsert_case first"
                    )
                run = AnalysisRunRow(
                    run_id=result.run_id,
                    case_id=result.case_id,
                    spec_hash=result.spec_hash,
                    data_mode=result.data_mode,
                    requested_by=requested_by,
                    created_at=created_at,
                )
                session.add(run)
                record_result(session, run, result, written_at=created_at)
        except sa.exc.IntegrityError as exc:
            with self._sessions() as session:
                if session.get(AnalysisRunRow, result.run_id) is not None:
                    raise DuplicateRunError(f"run {result.run_id!r} is already stored") from exc
            raise StoreError(f"the database refused run {result.run_id!r}: {exc.orig}") from exc

    # --- reading ---------------------------------------------------------------

    def by_run_id(self, run_id: str) -> AnalysisResult | None:
        """The stored result for ``run_id``, rebuilt exactly, or ``None``.

        ``None`` also for a run with no engine result yet: one that is queued, running,
        cancelled, or failed before the engine ran. Its job status says why.
        """
        with self._sessions() as session:
            run = session.get(AnalysisRunRow, run_id)
            if run is None or run.engine_status is None:
                return None
            return self._rebuild(session, run)

    def by_spec_hash(
        self, spec_hash: str, *, data_mode: DataMode, engine_version: str
    ) -> AnalysisResult | None:
        """The most recent finished result for a specification, or ``None``.

        "Most recent" is the latest ``created_at``; a tie is broken by ``run_id``,
        descending. That tiebreak is arbitrary but stable: the same query always
        returns the same run. Runs only tie when written within the same
        microsecond, so in practice it decides nothing real.

        If the newest match was written under a contract this code cannot read, this
        raises instead of falling back to an older run: quietly answering with a
        staler result is how a cache serves the wrong number.
        """
        query = (
            sa.select(AnalysisRunRow)
            .where(
                AnalysisRunRow.spec_hash == spec_hash,
                AnalysisRunRow.data_mode == data_mode,
                AnalysisRunRow.engine_version == engine_version,
                AnalysisRunRow.status == AnalysisStatus.SUCCEEDED.value,
            )
            .order_by(AnalysisRunRow.created_at.desc(), AnalysisRunRow.run_id.desc())
            .limit(1)
        )
        with self._sessions() as session:
            run = session.scalars(query).first()
            return None if run is None else self._rebuild(session, run)

    def list_for_case(
        self,
        case_id: str,
        *,
        data_mode: DataMode | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[RunSummary]:
        """Runs for a case, newest first, without opening any evidence document."""
        if limit < 1 or offset < 0:
            raise ValueError("limit must be at least 1 and offset must not be negative")
        query = _with_jobs().where(AnalysisRunRow.case_id == case_id)
        if data_mode is not None:
            query = query.where(AnalysisRunRow.data_mode == data_mode)
        query = (
            query.order_by(AnalysisRunRow.created_at.desc(), AnalysisRunRow.run_id.desc())
            .limit(limit)
            .offset(offset)
        )
        with self._sessions() as session:
            return [_summary(run, last_error) for run, last_error in session.execute(query)]

    def summary_for(self, run_id: str) -> RunSummary | None:
        """The run's summary, or ``None`` if there is no such run."""
        query = _with_jobs().where(AnalysisRunRow.run_id == run_id)
        with self._sessions() as session:
            row = session.execute(query).first()
            return None if row is None else _summary(row[0], row[1])

    def list_runs(
        self, filters: RunFilter, *, limit: int = 25, after: RunCursor | None = None
    ) -> RunPage:
        """A page of runs matching ``filters``, newest first, strictly after ``after``.

        Keyset pagination on ``(created_at, run_id)`` descending. Both are fixed when a
        run is created, so a cursor stays valid however many runs are written after
        it. Runs written later sort above the cursor and never shift a later page.
        One row more than ``limit`` is read to learn whether another page exists, so
        there is no ``COUNT`` (which would be slow, and stale as soon as it was read).

        One limit remains: a run whose transaction commits late can carry a
        ``created_at`` older than a position a reader has already passed. That run
        is missing from that scroll and appears in the next. It cannot cause a
        duplicate or a reordering.
        """
        if limit < 1:
            raise ValueError("limit must be at least 1")
        query = _with_jobs()
        if filters.case_id is not None:
            query = query.where(AnalysisRunRow.case_id == filters.case_id)
        if filters.statuses:
            query = query.where(AnalysisRunRow.status.in_(filters.statuses))
        if filters.engine_version is not None:
            query = query.where(AnalysisRunRow.engine_version == filters.engine_version)
        if filters.data_mode is not None:
            query = query.where(AnalysisRunRow.data_mode == filters.data_mode)
        if filters.created_after is not None:
            query = query.where(AnalysisRunRow.created_at >= filters.created_after)
        if filters.created_before is not None:
            query = query.where(AnalysisRunRow.created_at < filters.created_before)
        if filters.project_ids is not None:
            query = query.where(AnalysisRunRow.project_id.in_(filters.project_ids))
        if after is not None:
            query = query.where(
                sa.tuple_(AnalysisRunRow.created_at, AnalysisRunRow.run_id)
                < sa.tuple_(after.created_at, after.run_id)
            )
        query = query.order_by(
            AnalysisRunRow.created_at.desc(), AnalysisRunRow.run_id.desc()
        ).limit(limit + 1)

        with self._sessions() as session:
            rows = list(session.execute(query))
        page = [_summary(run, last_error) for run, last_error in rows[:limit]]
        next_cursor = None
        if len(rows) > limit and page:
            last = page[-1]
            next_cursor = RunCursor(created_at=last.created_at, run_id=last.run_id)
        return RunPage(items=tuple(page), next_cursor=next_cursor)

    # --- rebuilding ------------------------------------------------------------

    def _rebuild(self, session: Session, run: AnalysisRunRow) -> AnalysisResult:
        """Turn a stored run back into the exact ``AnalysisResult`` that was saved.

        Both contract versions are checked first. The run row is checked as well as
        the bundle because a refused run has no bundle, and its error document was
        still written under some contract.
        """
        check_readable(
            run.contract_version, run.run_id, what="run", consumer_version=self._consumer_version
        )
        if (
            run.engine_status is None
            or run.engine_version is None
            or run.engine_contract_version is None
        ):
            raise StoreError(f"run {run.run_id!r} has no finished engine result recorded")

        bundle = None
        if run.engine_status == EngineStatus.COMPLETED.value:
            bundle_row = session.get(EvidenceBundleRow, run.run_id)
            if bundle_row is None:
                raise StoreError(f"run {run.run_id!r} completed but has no stored bundle")
            bundle = load_bundle(bundle_row, consumer_version=self._consumer_version)

        return AnalysisResult(
            contract_version=run.contract_version,
            run_id=run.run_id,
            case_id=run.case_id,
            spec_hash=run.spec_hash,
            status=EngineStatus(run.engine_status),
            engine=EngineRef(
                engine_version=run.engine_version,
                contract_version=run.engine_contract_version,
                git_sha=run.engine_git_sha,
            ),
            datasets=tuple(DatasetRef.model_validate(d) for d in run.dataset_refs),
            seed=run.seed,
            data_mode=run.data_mode,
            started_at=_format_timestamp(run.started_at),
            finished_at=_format_timestamp(run.finished_at),
            bundle=bundle,
            error=AnalysisError.model_validate(run.error) if run.error is not None else None,
            metrics=RunMetrics.model_validate(run.metrics or {}),
        )
