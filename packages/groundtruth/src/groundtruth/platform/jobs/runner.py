"""One step of a worker: claim a job, run it, record what happened.

**Owner: Bhumi.**

The worker process (:mod:`groundtruth.platform.jobs.worker`) is a loop around
:func:`process`, plus what a long-lived process needs: a heartbeat thread
(``run_analysis`` blocks, and the lease must outlive it), signal handling and idle
waits. Keeping the step here means the parts most likely to be got wrong (the refusal
mapping and the cancellation checkpoints) are exercised by this package's tests rather
than only by a process.
"""

from __future__ import annotations

from collections.abc import Callable

from groundtruth.contracts.errors import DataUnavailableError
from groundtruth.contracts.ports import DataAccess
from groundtruth.contracts.request import AnalysisRequest
from groundtruth.contracts.result import AnalysisResult, AnalysisStatus
from groundtruth.engine import run_analysis
from groundtruth.logging import get_logger, log_context
from groundtruth.platform.jobs.lifecycle import JobCancelledError, LeaseLostError
from groundtruth.platform.jobs.queue import ClaimedJob, JobQueue
from groundtruth.platform.store.interface import StoreError

ResolveAccess = Callable[[AnalysisRequest], DataAccess]
"""Builds the data ports for a request (``platform.datasets``)."""

RunEngine = Callable[[AnalysisRequest, DataAccess], AnalysisResult]
"""The engine call. ``run_analysis`` in production; injectable for tests."""

logger = get_logger("jobs.runner")


def process_next(
    queue: JobQueue,
    worker_id: str,
    resolve_access: ResolveAccess,
    *,
    run: RunEngine = run_analysis,
) -> AnalysisStatus | None:
    """Claim and process one job. Returns its new status, or ``None`` if none was waiting.

    See :func:`process` for what happens to a claimed job.
    """
    job = queue.claim(worker_id)
    if job is None:
        return None
    return process(queue, job, resolve_access, run=run)


def process(
    queue: JobQueue,
    job: ClaimedJob,
    resolve_access: ResolveAccess,
    *,
    run: RunEngine = run_analysis,
) -> AnalysisStatus:
    """Process a job this worker has claimed. Returns its new status.

    Stages, with a cancellation checkpoint before each of the first two and one inside
    ``complete`` after the third:

    1. ``data``: resolve data access. ``DataUnavailableError`` is retryable: an outage
       can pass.
    2. ``engine``: run the engine. Whatever it returns, including a refusal, is a result.
    3. ``record``: record the result. A refusal becomes ``SUCCEEDED``, never ``FAILED``.

    Nothing is written until stage 3, and stage 3 is one transaction, so a crash at any
    point leaves no partial result: the job stays claimed until its lease expires and is
    then retried.

    A result that cannot be stored fails the job for good. Any other exception is a
    bug: the job is failed (not retried, since the same input fails the same way) and
    the exception is re-raised so the worker logs it loudly.

    Raises:
        LeaseLostError: if this worker lost the job mid-way. Another attempt owns it;
            the worker should log this and move on.
    """
    try:
        with log_context(stage="data"):
            queue.checkpoint(job, "before-data", begins="data")
            try:
                data = resolve_access(job.request)
            except DataUnavailableError as exc:
                logger.warning("data unavailable; the job will be retried if attempts remain")
                return queue.fail(job, f"data unavailable: {exc}", retryable=True)
            logger.info("data access ready (%s data)", job.request.data_mode)
        with log_context(stage="engine"):
            queue.checkpoint(job, "before-engine", begins="engine")
            logger.info("engine started")
            result = run(job.request, data)
            logger.info("engine finished with status %s", result.status.value)
        with log_context(stage="record"):
            try:
                status = queue.complete(job, result)
            except StoreError as exc:
                logger.error("result could not be stored: %s", exc)
                return queue.fail(job, f"result could not be stored: {exc}", retryable=False)
            logger.info("outcome recorded; the job is %s", status.value)
            return status
    except JobCancelledError:
        logger.info("cancelled at a checkpoint")
        return AnalysisStatus.CANCELLED
    except LeaseLostError:
        raise
    except Exception as exc:
        queue.fail(job, f"{type(exc).__name__}: {exc}", retryable=False)
        raise
