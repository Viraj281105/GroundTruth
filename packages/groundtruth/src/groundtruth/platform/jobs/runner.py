"""One step of a worker: claim a job, run it, record what happened.

**Owner: Bhumi.**

The worker process (issue #25) is a loop around :func:`process_next`, plus what a
long-lived process needs: a heartbeat thread (``run_analysis`` blocks, and the lease
must outlive it), signal handling and idle sleeps. Keeping the step here means the
parts most likely to be got wrong (the refusal mapping and the cancellation
checkpoints) are exercised by this package's tests rather than only by a process.
"""

from __future__ import annotations

from collections.abc import Callable

from groundtruth.contracts.errors import DataUnavailableError
from groundtruth.contracts.ports import DataAccess
from groundtruth.contracts.request import AnalysisRequest
from groundtruth.contracts.result import AnalysisResult, AnalysisStatus
from groundtruth.engine import run_analysis
from groundtruth.platform.jobs.lifecycle import JobCancelledError, LeaseLostError
from groundtruth.platform.jobs.queue import JobQueue
from groundtruth.platform.store.interface import StoreError

ResolveAccess = Callable[[AnalysisRequest], DataAccess]
"""Builds the data ports for a request (``platform.datasets``)."""

RunEngine = Callable[[AnalysisRequest, DataAccess], AnalysisResult]
"""The engine call. ``run_analysis`` in production; injectable for tests."""


def process_next(
    queue: JobQueue,
    worker_id: str,
    resolve_access: ResolveAccess,
    *,
    run: RunEngine = run_analysis,
) -> AnalysisStatus | None:
    """Claim and process one job. Returns its new status, or ``None`` if none was waiting.

    Stages, with a cancellation checkpoint before each of the first two and one inside
    ``complete`` after the third:

    1. resolve data access. ``DataUnavailableError`` is retryable: an outage can pass.
    2. run the engine. Whatever it returns, including a refusal, is a result.
    3. record the result. A refusal becomes ``SUCCEEDED``, never ``FAILED``.

    A result that cannot be stored fails the job for good. Any other exception is a
    bug: the job is failed (not retried, since the same input fails the same way) and
    the exception is re-raised so the worker logs it loudly.

    Raises:
        LeaseLostError: if this worker lost the job mid-way. Another attempt owns it;
            the worker should log this and move on.
    """
    job = queue.claim(worker_id)
    if job is None:
        return None
    try:
        queue.checkpoint(job, "before-data")
        try:
            data = resolve_access(job.request)
        except DataUnavailableError as exc:
            return queue.fail(job, f"data unavailable: {exc}", retryable=True)
        queue.checkpoint(job, "before-engine")
        result = run(job.request, data)
        try:
            return queue.complete(job, result)
        except StoreError as exc:
            return queue.fail(job, f"result could not be stored: {exc}", retryable=False)
    except JobCancelledError:
        return AnalysisStatus.CANCELLED
    except LeaseLostError:
        raise
    except Exception as exc:
        queue.fail(job, f"{type(exc).__name__}: {exc}", retryable=False)
        raise
