"""The analysis job state machine, retry policy and the job layer's errors.

**Owner: Bhumi.**

Two vocabularies meet here and must not be confused (ADR-008). ``AnalysisStatus`` is
the job: did the platform manage to run the analysis? ``EngineStatus`` is the science:
what did the engine find? A project the data cannot support is a *succeeded* job with
a *refused* result. Marking it failed would make the UI show a system error for the
system working correctly, so that mapping lives in exactly one place
(``platform.store.sql``) and the tests pin it from both ends.

Nothing here touches a database; :mod:`groundtruth.platform.jobs.queue` applies these
rules inside its transactions.
"""

from __future__ import annotations

from datetime import timedelta

from groundtruth.contracts.errors import GroundTruthError
from groundtruth.contracts.result import AnalysisStatus, ErrorCode

QUEUED = AnalysisStatus.QUEUED
RUNNING = AnalysisStatus.RUNNING
SUCCEEDED = AnalysisStatus.SUCCEEDED
FAILED = AnalysisStatus.FAILED
CANCELLED = AnalysisStatus.CANCELLED

TRANSITIONS: frozenset[tuple[AnalysisStatus, AnalysisStatus]] = frozenset(
    {
        (QUEUED, RUNNING),  # a worker claims it
        (QUEUED, CANCELLED),  # cancelled before anyone claimed it
        (RUNNING, SUCCEEDED),  # the engine completed *or refused*
        (RUNNING, FAILED),  # a non-retryable failure, or retries exhausted
        (RUNNING, QUEUED),  # a retryable failure or an expired lease, attempts left
        (RUNNING, CANCELLED),  # cancel seen at a checkpoint, or on an expired lease
    }
)
"""Every allowed status change. Terminal statuses have none."""

RETRYABLE_ENGINE_ERRORS: frozenset[ErrorCode] = frozenset({ErrorCode.DATA_UNAVAILABLE})
"""Engine errors worth another attempt.

The engine is deterministic: given the same request and data, an estimator that failed
to fit fails again, so retrying only burns compute. Only an upstream outage can pass.
Refusals never reach this check; they are successful jobs.
"""

DEFAULT_LEASE = timedelta(minutes=5)
"""How long a claim lasts without a heartbeat. A worker should beat every lease/3."""

DEFAULT_BACKOFF_BASE = timedelta(seconds=30)
DEFAULT_BACKOFF_CAP = timedelta(minutes=15)
DEFAULT_MAX_ATTEMPTS = 3


class JobError(GroundTruthError):
    """Base class for job lifecycle failures."""


class IllegalTransitionError(JobError):
    """A status change the state machine does not allow, or that lost a race."""

    def __init__(self, run_id: str, current: AnalysisStatus, target: AnalysisStatus) -> None:
        super().__init__(f"run {run_id!r} cannot move from {current.value} to {target.value}")
        self.run_id = run_id
        self.current = current
        self.target = target


class LeaseLostError(JobError):
    """This worker no longer holds the job: its lease expired and it was reclaimed.

    The worker must stop and write nothing. Another attempt owns the job now, and a
    stale result would overwrite it.
    """


class JobCancelledError(JobError):
    """Cancellation was requested and has now been honoured at a checkpoint."""


class JobNotFoundError(JobError):
    """No run exists with this id."""


def check_transition(
    current: AnalysisStatus, target: AnalysisStatus, run_id: str = "<unknown>"
) -> None:
    """Raise unless ``current -> target`` is an allowed transition.

    Raises:
        IllegalTransitionError: if it is not.
    """
    if (current, target) not in TRANSITIONS:
        raise IllegalTransitionError(run_id, current, target)


def backoff_delay(
    attempt: int,
    *,
    base: timedelta = DEFAULT_BACKOFF_BASE,
    cap: timedelta = DEFAULT_BACKOFF_CAP,
) -> timedelta:
    """Wait before retrying after failed attempt number ``attempt`` (1-based).

    ``min(base * 2**(attempt - 1), cap)``: 30 s, 60 s, 120 s ... up to 15 minutes. No
    random jitter, so a retry schedule is reproducible in tests and in logs.
    """
    if attempt < 1:
        raise ValueError(f"attempt numbers start at 1, got {attempt}")
    # Bounding the exponent keeps a runaway attempt count from overflowing timedelta.
    return min(base * 2 ** min(attempt - 1, 20), cap)
