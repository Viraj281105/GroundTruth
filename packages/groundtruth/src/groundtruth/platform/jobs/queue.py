"""A database-backed analysis job queue: submit, claim, heartbeat, finish, cancel.

**Owner: Bhumi.**

No broker. A job is an ``analysis_runs`` row (its status, the one source of truth)
plus a ``jobs`` row (attempts, lease, cancellation). Because both live in the database,
jobs survive a process restart: a new process simply finds them.

Three rules make this safe with several workers:

* **Every status change is a conditional write** (``... WHERE status = <expected>``).
  If another worker moved the job first, zero rows change and the loser is told,
  rather than both believing they won.
* **Claiming is one statement that writes first.** On SQLite that takes the write lock
  before reading, so concurrent claimers queue up instead of deadlocking; on
  PostgreSQL the candidate is picked ``FOR UPDATE SKIP LOCKED`` so workers pass each
  other, and the status is re-checked under the row lock.
* **A worker proves it still owns a job on every write** (``locked_by`` and the attempt
  number). A worker whose lease expired and whose job was reclaimed gets
  :class:`LeaseLostError` and cannot overwrite the new attempt's result.

Every timestamp comes from the injected clock, never the database's, so tests control
time and SQLite's one-second ``CURRENT_TIMESTAMP`` never decides an ordering.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, cast

import sqlalchemy as sa
from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session, aliased, sessionmaker

from groundtruth.contracts.identifiers import new_run_id
from groundtruth.contracts.request import AnalysisRequest
from groundtruth.contracts.result import (
    AnalysisError,
    AnalysisResult,
    AnalysisStatus,
    EngineStatus,
    RunMetrics,
)
from groundtruth.engine import ENGINE_VERSION
from groundtruth.platform.jobs.interface import JobStatus, Lane, Submission
from groundtruth.platform.jobs.lifecycle import (
    CANCELLED,
    DEFAULT_BACKOFF_BASE,
    DEFAULT_BACKOFF_CAP,
    DEFAULT_LEASE,
    DEFAULT_MAX_ATTEMPTS,
    FAILED,
    QUEUED,
    RETRYABLE_ENGINE_ERRORS,
    RUNNING,
    SUCCEEDED,
    IllegalTransitionError,
    JobCancelledError,
    JobNotFoundError,
    LeaseLostError,
    backoff_delay,
    check_transition,
)
from groundtruth.platform.store.interface import StoreError, UnknownCaseError
from groundtruth.platform.store.models import AnalysisRunRow, CaseRow, JobRow
from groundtruth.platform.store.sql import SqlEvidenceStore, failure_reason_for, record_result


def stored_request(run: AnalysisRunRow) -> AnalysisRequest:
    """Rebuild a run's stored request and prove it is the one its ``spec_hash`` names.

    Used by the worker before it runs a job and by the replay harness (#42) before it replays
    one: both must compute exactly what was submitted, never a request rebuilt from the case.

    Raises:
        StoreError: no request was stored, it does not validate, or it hashes differently.
    """
    if run.request is None:
        raise StoreError(f"run {run.run_id!r} has no stored request")
    try:
        request = AnalysisRequest.model_validate(run.request)
    except ValidationError as exc:
        raise StoreError(f"run {run.run_id!r} has an invalid stored request: {exc}") from exc
    if request.spec_hash != run.spec_hash:
        raise StoreError(
            f"run {run.run_id!r}: stored request hashes to {request.spec_hash}, "
            f"but the run is for {run.spec_hash}"
        )
    return request


_CLAIM_SCAN_LIMIT = 10
"""How many unusable jobs one claim may skip (failing each) before giving up."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ClaimedJob(BaseModel):
    """A job one worker holds. Pass it back to every later call as proof of ownership."""

    model_config = ConfigDict(frozen=True)

    run_id: str
    worker_id: str
    attempt: int
    """1 on the first claim. Together with ``worker_id`` it fences stale workers."""
    request: AnalysisRequest


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class JobQueue:
    """The job lifecycle over a SQL database.

    Args:
        session_factory: Sessions on the platform database (migrated to head).
        engine_version: The engine build that will run jobs. A stored result only
            answers a new request when it came from this version (R8). Defaults to the
            engine in this process.
        clock: Supplies "now" for every timestamp written or compared.
        lease: How long a claim lasts without a heartbeat.
        backoff_base: First retry delay; doubles each attempt.
        backoff_cap: Longest retry delay.
        max_attempts: Claims allowed per job before it fails for good.
        batch_max_running: At most this many ``batch`` jobs run at once, across every
            worker, so the rest stay free for interactive work (#47). ``None``: no limit.
            Interactive jobs are always claimed first either way.
    """

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        engine_version: str = ENGINE_VERSION,
        clock: Callable[[], datetime] = _utc_now,
        lease: timedelta = DEFAULT_LEASE,
        backoff_base: timedelta = DEFAULT_BACKOFF_BASE,
        backoff_cap: timedelta = DEFAULT_BACKOFF_CAP,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        batch_max_running: int | None = None,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if batch_max_running is not None and batch_max_running < 0:
            raise ValueError("batch_max_running must not be negative")
        self._batch_max_running = batch_max_running
        self._sessions = session_factory
        self._store = SqlEvidenceStore(session_factory, clock=clock)
        self._engine_version = engine_version
        self._clock = clock
        self._lease = lease
        self._backoff_base = backoff_base
        self._backoff_cap = backoff_cap
        self._max_attempts = max_attempts

    @property
    def lease(self) -> timedelta:
        """How long a claim lasts without a heartbeat."""
        return self._lease

    # --- submitting ------------------------------------------------------------

    def submit(
        self,
        request: AnalysisRequest,
        *,
        requested_by: str | None = None,
        project_id: str | None = None,
        lane: Lane = "batch",
    ) -> Submission:
        """Queue a request, unless a result or an identical job already exists.

        1. A stored result for the same ``spec_hash``, ``data_mode`` and engine version
           is returned as is (``from_cache``): the run is deterministic (ADR-006), so
           recomputing it would produce the same numbers. No new run is created;
           cloning the result under a new id would describe a run that never happened.
        2. An identical request already queued or running is returned
           (``deduplicated``) instead of being computed twice.
        3. Otherwise a new run and job are created, ``QUEUED``. The full request is
           stored with the run, so it executes exactly as submitted.

        ``requested_by`` and ``project_id`` are recorded on a new run (and the job carries
        the project too). ``lane`` is ``interactive`` when a person is waiting for the result
        (``POST /jobs``) and ``batch`` otherwise; workers take interactive jobs first. When an existing run answers instead, it is filed under
        ``project_id`` if it had none, so a legacy run the same caller asks for again becomes
        readable; a run already filed elsewhere is never moved.

        Raises:
            UnknownCaseError: if the case is not stored (``upsert_case`` first).
        """
        cached = self._store.by_spec_hash(
            request.spec_hash, data_mode=request.data_mode, engine_version=self._engine_version
        )
        if cached is not None:
            self._adopt(cached.run_id, project_id)
            return Submission(run_id=cached.run_id, status=SUCCEEDED, from_cache=True)

        now = self._clock()
        with self._sessions.begin() as session:
            in_flight = session.execute(
                sa.select(AnalysisRunRow.run_id, AnalysisRunRow.status)
                .join(JobRow, JobRow.run_id == AnalysisRunRow.run_id)
                .where(
                    AnalysisRunRow.spec_hash == request.spec_hash,
                    AnalysisRunRow.data_mode == request.data_mode,
                    AnalysisRunRow.status.in_([QUEUED.value, RUNNING.value]),
                    JobRow.cancel_requested_at.is_(None),
                )
                .order_by(AnalysisRunRow.created_at, AnalysisRunRow.run_id)
                .limit(1)
            ).first()
            if in_flight is not None:
                self._adopt_in(session, in_flight.run_id, project_id)
                return Submission(
                    run_id=in_flight.run_id,
                    status=AnalysisStatus(in_flight.status),
                    deduplicated=True,
                )
            if session.get(CaseRow, request.case_id) is None:
                raise UnknownCaseError(
                    f"case {request.case_id!r} is not stored; call upsert_case first"
                )

            run_id = new_run_id()
            session.add(
                AnalysisRunRow(
                    run_id=run_id,
                    case_id=request.case_id,
                    spec_hash=request.spec_hash,
                    status=QUEUED.value,
                    data_mode=request.data_mode,
                    is_simulated=request.is_simulated,
                    seed=request.seed,
                    contract_version=request.contract_version,
                    dataset_refs=[d.model_dump(mode="json") for d in request.datasets],
                    request=request.model_dump(mode="json"),
                    requested_by=requested_by,
                    project_id=project_id,
                    created_at=now,
                )
            )
            session.flush()  # the run must exist before the job references it
            session.add(
                JobRow(
                    run_id=run_id,
                    project_id=project_id,
                    attempts=0,
                    max_attempts=self._max_attempts,
                    lane=lane,
                    available_at=now,
                    created_at=now,
                    updated_at=now,
                )
            )
        return Submission(run_id=run_id, status=QUEUED)

    def _adopt(self, run_id: str, project_id: str | None) -> None:
        with self._sessions.begin() as session:
            self._adopt_in(session, run_id, project_id)

    @staticmethod
    def _adopt_in(session: Session, run_id: str, project_id: str | None) -> None:
        """File an unfiled run (and its job) under ``project_id``; never move a filed one."""
        if project_id is None:
            return
        for model in (AnalysisRunRow, JobRow):
            session.execute(
                sa.update(model)
                .where(model.run_id == run_id, model.project_id.is_(None))
                .values(project_id=project_id)
                .execution_options(synchronize_session=False)
            )

    # --- claiming --------------------------------------------------------------

    def claim(self, worker_id: str) -> ClaimedJob | None:
        """Take the next available job, or ``None`` if there is none.

        Expired leases are reaped first, so a job abandoned by a crashed worker comes
        back without any separate process. Jobs are taken oldest-available first.
        """
        self.reap_expired()
        for _ in range(_CLAIM_SCAN_LIMIT):
            claimed = self._claim_one(worker_id)
            if claimed is not False:
                return claimed
        return None

    def _candidate(self, now: datetime) -> sa.ScalarSelect[Any]:
        """The next claimable job id, as a subquery of the claim statement.

        Interactive jobs first, then batch, oldest first within a lane (#47). With
        ``batch_max_running`` set, a batch job is taken only while fewer than that many batch
        jobs are running; two workers claiming at the same instant can overshoot by one,
        which a cap meant to keep capacity free tolerates.
        """
        run = aliased(AnalysisRunRow)  # aliased so it cannot correlate with the UPDATE
        conditions = [
            run.status == QUEUED.value,
            JobRow.available_at <= now,
            JobRow.cancel_requested_at.is_(None),
        ]
        if self._batch_max_running is not None:
            other_job, other_run = aliased(JobRow), aliased(AnalysisRunRow)
            running_batch = (
                sa.select(sa.func.count())
                .select_from(other_job)
                .join(other_run, other_run.run_id == other_job.run_id)
                .where(other_job.lane == "batch", other_run.status == RUNNING.value)
                .scalar_subquery()
            )
            conditions.append(
                sa.or_(JobRow.lane == "interactive", running_batch < self._batch_max_running)
            )
        interactive_first = sa.case((JobRow.lane == "interactive", 0), else_=1)
        return (
            sa.select(JobRow.run_id)
            .join(run, run.run_id == JobRow.run_id)
            .where(*conditions)
            .order_by(interactive_first, JobRow.available_at, JobRow.run_id)
            .limit(1)
            .with_for_update(of=JobRow, skip_locked=True)  # PostgreSQL; SQLite ignores it
            .correlate(None)
            .scalar_subquery()
        )

    def _claim_statement(self, now: datetime) -> sa.Update:
        """Move the next queued job to running, in one statement that writes first."""
        return (
            sa.update(AnalysisRunRow)
            .where(
                AnalysisRunRow.run_id == self._candidate(now),
                AnalysisRunRow.status == QUEUED.value,  # re-checked under the row lock
            )
            .values(status=RUNNING.value)
            .returning(AnalysisRunRow.run_id)
            .execution_options(synchronize_session=False)
        )

    def _claim_one(self, worker_id: str) -> ClaimedJob | Literal[False] | None:
        """One claim attempt. ``False`` means "claimed an unusable job, try again"."""
        now = self._clock()
        with self._sessions.begin() as session:
            run_id = session.execute(self._claim_statement(now)).scalar_one_or_none()
            if run_id is None:
                return None
            session.execute(
                sa.update(JobRow)
                .where(JobRow.run_id == run_id)
                .values(
                    attempts=JobRow.attempts + 1,
                    locked_by=worker_id,
                    heartbeat_at=now,
                    lease_expires_at=now + self._lease,
                    stage="claim",
                    stage_log={"claim": now.isoformat()},
                    updated_at=now,
                )
                .execution_options(synchronize_session=False)
            )
            job = session.get(JobRow, run_id)
            run = session.get(AnalysisRunRow, run_id)
            assert job is not None and run is not None
            try:
                request = self._stored_request(run)
            except StoreError as exc:
                # Retrying cannot repair a stored specification, so this fails for good.
                self._finish(session, run, job, now, FAILED, _failure("unusable-request", exc))
                return False
            return ClaimedJob(
                run_id=run_id, worker_id=worker_id, attempt=job.attempts, request=request
            )

    @staticmethod
    def _stored_request(run: AnalysisRunRow) -> AnalysisRequest:
        """Rebuild the run's request and prove it is the one its ``spec_hash`` names."""
        return stored_request(run)

    # --- while running ---------------------------------------------------------

    def heartbeat(self, job: ClaimedJob) -> bool:
        """Renew the lease. Returns ``True`` if cancellation has been requested.

        Raises:
            LeaseLostError: if this worker no longer holds the job.
        """
        now = self._clock()
        with self._sessions.begin() as session:
            if not self._renew(session, job, now):
                raise LeaseLostError(_lost(job))
            return (
                session.scalar(
                    sa.select(JobRow.cancel_requested_at).where(JobRow.run_id == job.run_id)
                )
                is not None
            )

    def checkpoint(self, job: ClaimedJob, stage: str, *, begins: str | None = None) -> None:
        """Honour a pending cancellation between stages; otherwise renew the lease.

        ``run_analysis`` is one call that cannot be interrupted without changing the
        engine, so "between stages" means the job's own stages: before data access,
        before the engine, and (inside :meth:`complete`) after it.

        ``begins`` names the live stage that starts once the checkpoint passes, so a
        poller can see it. It is written in the same transaction as the lease renewal
        and the cancel check, and not at all if the job is cancelled here: a stage that
        never began is not shown as begun.

        Raises:
            JobCancelledError: if cancellation was requested; the job is now CANCELLED.
            LeaseLostError: if this worker no longer holds the job.
        """
        now = self._clock()
        with self._sessions.begin() as session:
            if not self._renew(session, job, now):
                raise LeaseLostError(_lost(job))
            row, run = self._rows(session, job.run_id)
            cancelled = row.cancel_requested_at is not None
            if cancelled:
                self._finish(session, run, row, now, CANCELLED, _cancelled(stage))
            elif begins is not None:
                _enter_stage(row, begins, now)
        if cancelled:
            raise JobCancelledError(f"run {job.run_id!r} was cancelled at {stage}")

    # --- finishing -------------------------------------------------------------

    def complete(self, job: ClaimedJob, result: AnalysisResult) -> AnalysisStatus:
        """Record the engine's result for this job and return the job's new status.

        The result is relabelled with the job's ``run_id``: the engine mints its own
        id, but the job's id is the one callers were given and are polling. Nothing
        else in a result refers to the id, so no number changes.

        * Engine ``completed`` or ``refused`` -> ``SUCCEEDED``. A refusal is the system
          working correctly, never a failed job.
        * Engine ``error`` with a retryable code and attempts left -> ``QUEUED`` again,
          after backoff. This attempt's result is kept in ``last_error`` only; a run is
          written once, so only the final attempt's result is stored.
        * Any other engine ``error`` -> ``FAILED``, with its error stored.
        * Cancellation requested while the engine ran -> ``CANCELLED``; the result is
          discarded, so a cancelled job never carries a result.

        Raises:
            LeaseLostError: if this worker no longer holds the job.
            StoreError: if the result cannot be stored for this run (it belongs to a
                different specification, or the database refuses it).
        """
        result = result.model_copy(update={"run_id": job.run_id})
        now = self._clock()
        try:
            with self._sessions.begin() as session:
                if not self._renew(session, job, now):
                    raise LeaseLostError(_lost(job))
                row, run = self._rows(session, job.run_id)
                if row.cancel_requested_at is not None:
                    return self._finish(session, run, row, now, CANCELLED, _cancelled("engine"))
                _enter_stage(row, "record", now)
                error = result.error
                if (
                    result.status is EngineStatus.ERROR
                    and error is not None
                    and error.code in RETRYABLE_ENGINE_ERRORS
                    and row.attempts < row.max_attempts
                ):
                    return self._requeue(
                        session, run, row, now,
                        {"reason": "engine-error", "attempt": row.attempts,
                         "error": error.model_dump(mode="json")},
                    )  # fmt: skip
                target = FAILED if result.status is EngineStatus.ERROR else SUCCEEDED
                check_transition(AnalysisStatus(run.status), target, job.run_id)
                record_result(session, run, result, written_at=now)
                _release(row, now)
                if error is not None and result.status is EngineStatus.ERROR:
                    row.last_error = {
                        "reason": "engine-error",
                        "attempt": row.attempts,
                        "error": error.model_dump(mode="json"),
                    }
                return AnalysisStatus(run.status)
        except sa.exc.IntegrityError as exc:
            raise StoreError(
                f"the database refused the result for {job.run_id!r}: {exc.orig}"
            ) from exc

    def fail(self, job: ClaimedJob, reason: str, *, retryable: bool) -> AnalysisStatus:
        """Record a failure outside the engine (data access, a crash) for this job.

        Retryable with attempts left -> ``QUEUED`` after backoff; otherwise ``FAILED``.
        If cancellation was requested, the job is ``CANCELLED`` instead of retried.

        Raises:
            LeaseLostError: if this worker no longer holds the job.
        """
        now = self._clock()
        with self._sessions.begin() as session:
            if not self._renew(session, job, now):
                raise LeaseLostError(_lost(job))
            row, run = self._rows(session, job.run_id)
            detail = {"reason": reason, "attempt": row.attempts, "retryable": retryable}
            if row.cancel_requested_at is not None:
                return self._finish(session, run, row, now, CANCELLED, detail)
            if retryable and row.attempts < row.max_attempts:
                return self._requeue(session, run, row, now, detail)
            return self._finish(session, run, row, now, FAILED, detail)

    # --- cancelling ------------------------------------------------------------

    def cancel(self, run_id: str) -> AnalysisStatus:
        """Cancel a job. Returns its status afterwards.

        A queued job is cancelled at once (``CANCELLED``). A running one is flagged and
        stays ``RUNNING`` until its worker reaches a checkpoint or its lease expires.
        Cancelling twice is harmless.

        Raises:
            JobNotFoundError: if there is no such run.
            IllegalTransitionError: if it already succeeded or failed.
        """
        now = self._clock()
        with self._sessions.begin() as session:
            moved = session.execute(
                sa.update(AnalysisRunRow)
                .where(AnalysisRunRow.run_id == run_id, AnalysisRunRow.status == QUEUED.value)
                .values(status=CANCELLED.value)
                .execution_options(synchronize_session=False)
            )
            if _rowcount(moved):
                session.execute(
                    sa.update(JobRow)
                    .where(JobRow.run_id == run_id)
                    .values(cancel_requested_at=now, updated_at=now)
                    .execution_options(synchronize_session=False)
                )
                return CANCELLED
            flagged = session.execute(
                sa.update(JobRow)
                .where(
                    JobRow.run_id == run_id,
                    JobRow.cancel_requested_at.is_(None),
                    JobRow.run_id.in_(
                        sa.select(AnalysisRunRow.run_id).where(
                            AnalysisRunRow.run_id == run_id,
                            AnalysisRunRow.status == RUNNING.value,
                        )
                    ),
                )
                .values(cancel_requested_at=now, updated_at=now)
                .execution_options(synchronize_session=False)
            )
            if _rowcount(flagged):
                return RUNNING
            current = session.scalar(
                sa.select(AnalysisRunRow.status).where(AnalysisRunRow.run_id == run_id)
            )
        if current is None:
            raise JobNotFoundError(f"no run {run_id!r}")
        status = AnalysisStatus(current)
        if status in (CANCELLED, RUNNING):  # already cancelled, or already requested
            return status
        raise IllegalTransitionError(run_id, status, CANCELLED)

    # --- leases ----------------------------------------------------------------

    def reap_expired(self) -> int:
        """Return jobs whose lease has lapsed. Returns how many were reaped.

        For each running job past ``lease_expires_at``, in this order:

        * cancellation requested -> ``CANCELLED``
        * attempts used up -> ``FAILED``
        * otherwise -> ``QUEUED`` after backoff, so a job that keeps killing its worker
          cannot monopolise the queue.

        Each step is a write that re-checks ``status == running``, so two processes
        reaping at once cannot both act on the same job.
        """
        now = self._clock()
        expired = sa.select(JobRow.run_id).where(JobRow.lease_expires_at < now)
        steps = (
            (CANCELLED, expired.where(JobRow.cancel_requested_at.is_not(None))),
            (FAILED, expired.where(JobRow.attempts >= JobRow.max_attempts)),
            (QUEUED, expired),
        )
        reaped = 0
        with self._sessions.begin() as session:
            for target, which in steps:
                run_ids = session.scalars(
                    sa.update(AnalysisRunRow)
                    .where(
                        AnalysisRunRow.status == RUNNING.value,
                        AnalysisRunRow.run_id.in_(which),
                    )
                    .values(status=target.value)
                    .returning(AnalysisRunRow.run_id)
                    .execution_options(synchronize_session=False)
                ).all()
                for run_id in run_ids:
                    row = session.get(JobRow, run_id)
                    assert row is not None
                    detail = {
                        "reason": "lease-expired",
                        "attempt": row.attempts,
                        "worker": row.locked_by,
                    }
                    available_at = now + self._backoff(row.attempts) if target is QUEUED else None
                    _release(row, now, detail, available_at=available_at)
                reaped += len(run_ids)
        return reaped

    # --- reading ---------------------------------------------------------------

    def status(self, run_id: str) -> JobStatus | None:
        """The run's lifecycle state, or ``None`` if there is no such run."""
        with self._sessions() as session:
            run = session.get(AnalysisRunRow, run_id)
            if run is None:
                return None
            row = session.get(JobRow, run_id)
            # Read from the run row's small JSON columns. Rebuilding the whole result
            # would deserialise the evidence bundle on every poll.
            try:
                error = AnalysisError.model_validate(run.error) if run.error else None
            except ValidationError:  # a code added by a later contract minor
                error = None
            return JobStatus(
                run_id=run.run_id,
                case_id=run.case_id,
                project_id=run.project_id,
                status=AnalysisStatus(run.status),
                engine_status=run.engine_status,
                data_mode=run.data_mode,
                is_simulated=run.is_simulated,
                attempts=row.attempts if row else None,
                max_attempts=row.max_attempts if row else None,
                available_at=_as_utc(row.available_at) if row else None,
                lease_expires_at=_as_utc(row.lease_expires_at) if row else None,
                locked_by=row.locked_by if row else None,
                cancel_requested=bool(row and row.cancel_requested_at is not None),
                last_error=row.last_error if row else None,
                created_at=_require_utc(run.created_at),
                updated_at=_as_utc(row.updated_at) if row else None,
                heartbeat_at=_as_utc(row.heartbeat_at) if row else None,
                stage=row.stage if row else None,
                stage_log=_parse_stage_log(row.stage_log) if row else {},
                metrics=RunMetrics.model_validate(run.metrics) if run.metrics else None,
                error=error,
                failure_reason=failure_reason_for(run, row.last_error if row else None),
                as_of=self._clock(),
            )

    # --- internals -------------------------------------------------------------

    def _backoff(self, attempt: int) -> timedelta:
        return backoff_delay(attempt, base=self._backoff_base, cap=self._backoff_cap)

    def _renew(self, session: Session, job: ClaimedJob, now: datetime) -> bool:
        """Extend the lease if this worker still owns the running job. Writes first.

        Ownership is the worker id *and* the attempt number: a worker that reclaims its
        own expired job holds a new attempt, and its old attempt is fenced out.
        """
        renewed = session.execute(
            sa.update(JobRow)
            .where(
                JobRow.run_id == job.run_id,
                JobRow.locked_by == job.worker_id,
                JobRow.attempts == job.attempt,
                JobRow.run_id.in_(
                    sa.select(AnalysisRunRow.run_id).where(
                        AnalysisRunRow.run_id == job.run_id,
                        AnalysisRunRow.status == RUNNING.value,
                    )
                ),
            )
            .values(heartbeat_at=now, lease_expires_at=now + self._lease, updated_at=now)
            .execution_options(synchronize_session=False)
        )
        return _rowcount(renewed) == 1

    @staticmethod
    def _rows(session: Session, run_id: str) -> tuple[JobRow, AnalysisRunRow]:
        row = session.get(JobRow, run_id)
        run = session.get(AnalysisRunRow, run_id)
        assert row is not None and run is not None
        return row, run

    def _finish(
        self,
        session: Session,
        run: AnalysisRunRow,
        row: JobRow,
        now: datetime,
        target: AnalysisStatus,
        detail: dict[str, Any],
    ) -> AnalysisStatus:
        check_transition(AnalysisStatus(run.status), target, run.run_id)
        run.status = target.value
        _release(row, now, detail)
        return target

    def _requeue(
        self,
        session: Session,
        run: AnalysisRunRow,
        row: JobRow,
        now: datetime,
        detail: dict[str, Any],
    ) -> AnalysisStatus:
        check_transition(AnalysisStatus(run.status), QUEUED, run.run_id)
        run.status = QUEUED.value
        _release(row, now, detail, available_at=now + self._backoff(row.attempts))
        return QUEUED


def _release(
    row: JobRow,
    now: datetime,
    detail: dict[str, Any] | None = None,
    *,
    available_at: datetime | None = None,
) -> None:
    """Drop the lease, record why, and (when requeued) when the job may run again."""
    row.locked_by = None
    row.heartbeat_at = None
    row.lease_expires_at = None
    row.updated_at = now
    if detail is not None:
        row.last_error = detail
    if available_at is not None:
        row.available_at = available_at
        # Waiting to run again: the failed attempt's progress is not this job's progress.
        row.stage = None
        row.stage_log = None


def _enter_stage(row: JobRow, stage: str, now: datetime) -> None:
    """Record that ``stage`` began now. The log is reassigned so the change is saved."""
    row.stage = stage
    row.stage_log = {**(row.stage_log or {}), stage: now.isoformat()}


def _require_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _parse_stage_log(log: dict[str, str] | None) -> dict[str, datetime]:
    return {stage: _require_utc(datetime.fromisoformat(at)) for stage, at in (log or {}).items()}


def _rowcount(result: sa.Result[Any]) -> int:
    """Rows a conditional write changed: 0 means another writer got there first."""
    return cast(CursorResult[Any], result).rowcount


def _lost(job: ClaimedJob) -> str:
    return (
        f"worker {job.worker_id!r} no longer holds run {job.run_id!r} "
        f"(attempt {job.attempt}): its lease expired and the job moved on"
    )


def _cancelled(stage: str) -> dict[str, Any]:
    return {"reason": "cancelled", "stage": stage}


def _failure(reason: str, exc: Exception) -> dict[str, Any]:
    return {"reason": reason, "message": str(exc), "retryable": False}
