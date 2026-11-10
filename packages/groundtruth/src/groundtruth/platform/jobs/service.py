"""The job layer as the API uses it: a case store and a queue behind one small interface.

**Owner: Bhumi.**

The API does not hold a ``JobQueue`` directly. It holds a :class:`JobControl`, and this is
the SQL-backed one. Submitting stores the case first because a run must belong to a stored
case, which is the same step the ``groundtruth submit`` command takes.
"""

from __future__ import annotations

from groundtruth.contracts.request import AnalysisRequest
from groundtruth.contracts.result import AnalysisStatus
from groundtruth.platform.cases.registry import CaseDefinition
from groundtruth.platform.jobs.interface import JobStatus, Lane, Submission
from groundtruth.platform.jobs.queue import JobQueue
from groundtruth.platform.store.sql import SqlEvidenceStore


class SqlJobService:
    """Submit, cancel and inspect jobs on the platform database."""

    def __init__(self, store: SqlEvidenceStore, queue: JobQueue) -> None:
        self._store = store
        self._queue = queue

    def submit(
        self,
        case: CaseDefinition,
        request: AnalysisRequest,
        *,
        requested_by: str | None = None,
        project_id: str | None = None,
        lane: Lane = "batch",
    ) -> Submission:
        """Store the case, then queue the request (or return its result or in-flight job)."""
        self._store.upsert_case(case)
        return self._queue.submit(
            request, requested_by=requested_by, project_id=project_id, lane=lane
        )

    def cancel(self, run_id: str) -> AnalysisStatus:
        """Cancel a job; see :meth:`JobQueue.cancel`."""
        return self._queue.cancel(run_id)

    def status(self, run_id: str) -> JobStatus | None:
        """The job's state, or ``None`` if there is no such run."""
        return self._queue.status(run_id)
