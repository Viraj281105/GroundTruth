"""The worker loop and its heartbeat thread.

**Owner: Bhumi.**

A worker claims a job, keeps its lease alive from a background thread while the engine
runs, records the outcome, and repeats. It is the same ``run_analysis`` the API calls;
moving execution here changes neither the engine nor the contract (ADR-008).

What a worker deliberately does not do:

* **interrupt the engine.** ``run_analysis`` is one call. A cancel requested while it
  runs is seen by the heartbeat and honoured when it returns: the result is discarded
  and the job ends ``CANCELLED`` (the job layer's after-engine checkpoint).
* **write anything before the engine finishes.** The result reaches the database in
  one transaction, so a crash at any point leaves no partial result; the lease then
  expires and another attempt runs the job.
* **die on one bad job.** A bug fails that job and is logged with its traceback; the
  worker moves on. Only a stop request, or a second signal, ends it.
"""

from __future__ import annotations

import os
import socket
import threading
import uuid
from types import TracebackType
from typing import Any

import sqlalchemy as sa

from groundtruth.contracts.ports import DataAccess
from groundtruth.contracts.request import AnalysisRequest
from groundtruth.contracts.result import AnalysisResult, AnalysisStatus
from groundtruth.engine import run_analysis
from groundtruth.logging import current_log_context, get_logger, log_context
from groundtruth.platform.datasets.access import earth_engine_access, synthetic_access
from groundtruth.platform.jobs.lifecycle import LeaseLostError
from groundtruth.platform.jobs.queue import ClaimedJob, JobQueue
from groundtruth.platform.jobs.runner import ResolveAccess, RunEngine, process

logger = get_logger("worker")

DEFAULT_POLL_SECONDS = 2.0
"""How long an idle worker waits before looking for work again."""

DEFAULT_TRUE_EFFECT = 0.06
"""Effect injected into simulated runs; the same default as the API and ``verify``."""

_HEARTBEAT_JOIN_SECONDS = 10.0
_DB_RETRY_INITIAL_SECONDS = 2.0
_DB_RETRY_MAX_SECONDS = 60.0


def new_worker_id() -> str:
    """Unique per process, readable in logs: host, process id, and a random suffix."""
    return f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:6]}"[:100]


def default_resolve_access(true_effect: float = DEFAULT_TRUE_EFFECT) -> ResolveAccess:
    """Data access by the request's declared ``data_mode``.

    Simulated requests get the synthetic fixture, whose provenance marks every value as
    simulated. Observed requests get the Earth Engine path, which raises until it is
    implemented (#22): never a fixture under a real-data label (R7).
    """

    def resolve(request: AnalysisRequest) -> DataAccess:
        if request.data_mode == "simulated":
            return synthetic_access(request, true_effect=true_effect)
        return earth_engine_access(request)

    return resolve


def engine_runner(git_sha: str | None) -> RunEngine:
    """``run_analysis`` that records the commit this process runs, or ``None`` if unknown."""

    def run(request: AnalysisRequest, data: DataAccess) -> AnalysisResult:
        return run_analysis(request, data, git_sha=git_sha)

    return run


class Heartbeat:
    """Renews a job's lease from a background thread for as long as the block runs.

    ``run_analysis`` blocks the worker's main thread, so without this a long analysis
    would outlive its lease and be handed to another worker. Beats every ``interval``
    seconds; stopping wakes the thread at once rather than waiting out the interval.

    Nothing that goes wrong in the thread escapes it:

    * a pending cancel is logged once; the job layer honours it when the engine returns
    * a lost lease is logged and ends the beating; the job layer then refuses this
      worker's result, so nothing stale is written
    * anything else (a database blip) is logged and retried at the next beat, since the
      lease tolerates missed beats
    """

    def __init__(self, queue: JobQueue, job: ClaimedJob, interval: float) -> None:
        if interval <= 0:
            raise ValueError("heartbeat interval must be positive")
        self._queue = queue
        self._job = job
        self._interval = interval
        self._stop = threading.Event()
        self._context: dict[str, Any] = {}
        self._thread = threading.Thread(
            target=self._beat, name=f"heartbeat-{job.run_id}", daemon=True
        )
        self.beats = 0
        self.cancel_requested = False
        self.lease_lost = False

    def __enter__(self) -> Heartbeat:
        # Threads do not inherit context variables; hand the job's context over.
        self._context = current_log_context()
        self._thread.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.stop()

    def stop(self) -> None:
        """Stop beating and wait for the thread to finish. Safe to call more than once."""
        self._stop.set()
        if self._thread.ident is not None and self._thread.is_alive():
            self._thread.join(timeout=_HEARTBEAT_JOIN_SECONDS)
            if self._thread.is_alive():
                logger.warning(
                    "heartbeat thread did not stop within %.0fs", _HEARTBEAT_JOIN_SECONDS
                )

    @property
    def alive(self) -> bool:
        return self._thread.is_alive()

    def _beat(self) -> None:
        with log_context(**self._context, stage="heartbeat"):
            while not self._stop.wait(self._interval):
                try:
                    cancel = self._queue.heartbeat(self._job)
                except LeaseLostError:
                    self.lease_lost = True
                    logger.warning("lease lost; this worker's result will not be recorded")
                    return
                except Exception:
                    logger.warning("heartbeat failed; retrying at the next beat", exc_info=True)
                    continue
                self.beats += 1
                if cancel and not self.cancel_requested:
                    self.cancel_requested = True
                    logger.info(
                        "cancel requested; it is honoured when the engine returns, and the "
                        "result is then discarded"
                    )


class Worker:
    """Claims and processes jobs until asked to stop.

    Args:
        queue: The job queue to consume.
        worker_id: Identifies this worker's claims. Defaults to :func:`new_worker_id`.
        resolve_access: Data access for a request. Defaults to the simulated path for
            simulated requests and the (unimplemented) Earth Engine path otherwise.
        run: The engine call. Defaults to ``run_analysis`` with no commit recorded.
        poll_interval: Seconds to wait when the queue is empty.
        heartbeat_interval: Seconds between lease renewals. Defaults to a third of the
            queue's lease, so two missed beats are tolerated.
        db_retry_initial: First wait after the database is unreachable; doubles to a
            minute.
    """

    def __init__(
        self,
        queue: JobQueue,
        *,
        worker_id: str | None = None,
        resolve_access: ResolveAccess | None = None,
        run: RunEngine | None = None,
        poll_interval: float = DEFAULT_POLL_SECONDS,
        heartbeat_interval: float | None = None,
        db_retry_initial: float = _DB_RETRY_INITIAL_SECONDS,
    ) -> None:
        self.worker_id = worker_id or new_worker_id()
        self._queue = queue
        self._resolve = resolve_access or default_resolve_access()
        self._run = run or engine_runner(None)
        self._poll = poll_interval
        self._heartbeat_interval = heartbeat_interval or queue.lease.total_seconds() / 3
        self._db_retry_initial = db_retry_initial
        self._stop = threading.Event()

    def request_stop(self) -> None:
        """Stop after the current job, if any. Wakes an idle worker at once."""
        self._stop.set()

    @property
    def stopping(self) -> bool:
        return self._stop.is_set()

    def run(self, *, exit_when_idle: bool = False, max_jobs: int | None = None) -> int:
        """Process jobs until stopped. Returns how many jobs were processed.

        Args:
            exit_when_idle: Return as soon as the queue is empty, instead of waiting.
            max_jobs: Return after this many jobs.
        """
        processed = 0
        db_wait = self._db_retry_initial
        with log_context(worker_id=self.worker_id):
            while not self._stop.is_set():
                if max_jobs is not None and processed >= max_jobs:
                    break
                try:
                    job = self._queue.claim(self.worker_id)
                except sa.exc.DBAPIError:
                    logger.warning(
                        "database unavailable; retrying in %.1fs", db_wait, exc_info=True
                    )
                    self._stop.wait(db_wait)
                    db_wait = min(db_wait * 2, _DB_RETRY_MAX_SECONDS)
                    continue
                db_wait = self._db_retry_initial
                if job is None:
                    if exit_when_idle:
                        break
                    self._stop.wait(self._poll)
                    continue
                self.run_job(job)
                processed += 1
        return processed

    def run_job(self, job: ClaimedJob) -> AnalysisStatus | None:
        """Process one claimed job with a heartbeat running. ``None`` if the lease was lost.

        A crash (an exception that is not an ``Exception``, such as a second interrupt)
        propagates after the heartbeat stops. Nothing has been written by then, and the
        job's lease will expire and return it to the queue.
        """
        context = {
            "run_id": job.run_id,
            "case_id": job.request.case_id,
            "attempt": job.attempt,
            "data_mode": job.request.data_mode,
        }
        with log_context(**context):
            logger.info("job claimed", extra={"stage": "claim"})
            with Heartbeat(self._queue, job, self._heartbeat_interval) as heartbeat:

                def run_then_stop_beating(
                    request: AnalysisRequest, data: DataAccess
                ) -> AnalysisResult:
                    # The heartbeat exists to outlive the engine. Once it returns, recording
                    # takes one short transaction that renews the lease itself; beating on
                    # would race it and report a finished job as a lost lease.
                    try:
                        return self._run(request, data)
                    finally:
                        heartbeat.stop()

                try:
                    status = process(self._queue, job, self._resolve, run=run_then_stop_beating)
                except LeaseLostError:
                    logger.warning(
                        "lost the job to another attempt; nothing from this run was recorded",
                        extra={"stage": "record"},
                    )
                    return None
                except Exception:
                    logger.exception(
                        "job failed with an unexpected error; the worker carries on",
                        extra={"stage": "record"},
                    )
                    return self._status_after_error(job)
            logger.info(
                "job finished: %s", status.value, extra={"stage": "done", "status": status.value}
            )
            return status

    def _status_after_error(self, job: ClaimedJob) -> AnalysisStatus | None:
        """Where an errored job ended up: FAILED if that could be recorded.

        If the database was unreachable even to record the failure, the job is still
        claimed; its lease expires and it is retried. Then there is no status to report.
        """
        try:
            status = self._queue.status(job.run_id)
        except Exception:
            logger.warning("could not read the job's status after the error", exc_info=True)
            return None
        return status.status if status is not None else None
