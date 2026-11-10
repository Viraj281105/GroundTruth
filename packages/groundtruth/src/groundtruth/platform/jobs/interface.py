"""What callers may ask of the job layer, and what it answers.

**Owner: Bhumi.**

The API depends on this module and never on SQLAlchemy, so it stays importable without
the ``db`` extra. The queue in :mod:`groundtruth.platform.jobs.queue` implements it, and
re-exports ``Submission`` and ``JobStatus`` so earlier imports keep working.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict

from groundtruth.contracts.request import AnalysisRequest
from groundtruth.contracts.result import AnalysisError, AnalysisStatus, RunMetrics
from groundtruth.platform.cases.registry import CaseDefinition
from groundtruth.platform.store.interface import ResultState, result_state_of

LIVE_STAGES: tuple[str, ...] = ("claim", "data", "engine", "record")
"""The stages a worker moves a job through, in order. The names the worker logs."""

Lane = Literal["interactive", "batch"]
"""``interactive``: a person is waiting for the result (POST /jobs). ``batch``: anything else.
Workers take interactive jobs first (#47)."""


class Submission(BaseModel):
    """What ``submit`` did with a request."""

    model_config = ConfigDict(frozen=True)

    run_id: str
    status: AnalysisStatus
    from_cache: bool = False
    """An existing result answered the request. No job was created and nothing ran."""
    deduplicated: bool = False
    """An identical request was already queued or running; this is that job."""


class JobStatus(BaseModel):
    """A run's lifecycle state, for polling. Job fields are ``None`` for a run with no job."""

    model_config = ConfigDict(frozen=True)

    run_id: str
    case_id: str
    project_id: str | None = None
    """The tenant project the run is filed under. Internal: authorization reads it, and the
    HTTP API does not expose it. ``None`` for a legacy run, which nobody may read."""
    status: AnalysisStatus
    engine_status: str | None
    """``refused`` here with ``status == succeeded`` is a legitimate scientific outcome."""
    data_mode: str
    is_simulated: bool
    """Always present, so nothing that shows a job can show a simulated run as observed (R7)."""
    attempts: int | None
    max_attempts: int | None
    available_at: datetime | None
    lease_expires_at: datetime | None
    locked_by: str | None
    """Which worker holds the job. Internal: the HTTP API deliberately does not expose it."""
    cancel_requested: bool
    last_error: dict[str, object] | None
    created_at: datetime
    """When the run was recorded (queued)."""
    updated_at: datetime | None
    """When the job last changed; for a finished job, when it finished."""
    heartbeat_at: datetime | None
    stage: str | None
    """The live stage the job is in now, if a worker has recorded one."""
    stage_log: dict[str, datetime]
    """When each live stage began. A stage ends when the next begins."""
    metrics: RunMetrics | None
    """The engine's own timings, present only once the engine has returned."""
    error: AnalysisError | None
    failure_reason: str | None
    """Why the job failed, when no engine error was stored for it."""
    as_of: datetime
    """The queue's clock when this was read; elapsed times are measured against it."""

    @property
    def result_state(self) -> ResultState:
        """The UI's vocabulary, from the same function ``/runs`` uses."""
        return result_state_of(self.status.value, self.engine_status)

    @property
    def terminal(self) -> bool:
        """True once nothing further will happen to the job; a client can stop polling."""
        return self.status.is_terminal


class JobControl(Protocol):
    """Submit, cancel and inspect jobs."""

    def submit(
        self,
        case: CaseDefinition,
        request: AnalysisRequest,
        *,
        requested_by: str | None = None,
        project_id: str | None = None,
        lane: Lane = "batch",
    ) -> Submission:
        """Queue ``request`` for ``case``, or return the existing result or in-flight job.

        ``lane`` is ``interactive`` when a person is waiting for the result, else ``batch``.

        The case is stored first, because a run must belong to a stored case.
        ``requested_by`` (a user id) and ``project_id`` are recorded on the run and job.
        """
        ...

    def cancel(self, run_id: str) -> AnalysisStatus:
        """Cancel a job; see :meth:`groundtruth.platform.jobs.queue.JobQueue.cancel`.

        Raises:
            JobNotFoundError: if there is no such run.
            IllegalTransitionError: if the job already succeeded or failed.
        """
        ...

    def status(self, run_id: str) -> JobStatus | None:
        """The job's state, or ``None`` if there is no such run."""
        ...
