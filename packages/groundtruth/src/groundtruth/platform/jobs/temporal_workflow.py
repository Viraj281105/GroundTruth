"""Run an analysis as a resumable Temporal workflow around the existing runner.

**Optional.** ``temporalio`` is imported lazily; nothing else in the package needs it.

Jobs are still submitted to, and stored in, the SQL queue. The workflow adds durable
execution: its single activity claims the next available job and runs the existing
:func:`~groundtruth.platform.jobs.runner.process` on it, heartbeating while it works. If
the worker dies, Temporal retries the activity on another worker; the SQL queue reaps the
expired lease on ``claim`` and hands the same job back. That retry is safe because the
runner writes nothing until its single-transaction ``record`` stage. Cancelling a run goes
through ``JobQueue.cancel`` as before; the runner honours it at its next checkpoint.

Usage (a maintainer's ``worker_temporal.py``)::

    from groundtruth.platform.jobs.temporal_workflow import build_worker, start_analysis
    worker = await build_worker(client, queue, resolve_access)   # then: await worker.run()
    handle = await start_analysis(client, run_id)                # after queue.submit(...)
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

from groundtruth.platform.jobs.queue import JobQueue
from groundtruth.platform.jobs.runner import ResolveAccess, RunEngine, process

TASK_QUEUE = "groundtruth-analysis"
ACTIVITY_NAME = "run_analysis_activity"
WORKFLOW_NAME = "AnalysisWorkflow"
IDLE = "idle"
"""Activity result when no job was waiting (another worker already took it)."""


def _require() -> tuple[Any, Any]:
    try:
        from temporalio import activity, workflow
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise ImportError(
            "the Temporal backend needs the 'temporalio' package; "
            "install it with: pip install temporalio"
        ) from exc
    return activity, workflow


def make_activity(
    queue: JobQueue,
    resolve_access: ResolveAccess,
    *,
    worker_id: str = "temporal",
    run: RunEngine | None = None,
) -> Any:
    """The activity: claim the next job and run the existing ``process`` on it.

    Returns the final ``AnalysisStatus`` value, or :data:`IDLE`.
    """
    activity, _ = _require()
    from groundtruth.engine import run_analysis

    engine = run or run_analysis

    @activity.defn(name=ACTIVITY_NAME)
    async def run_analysis_activity(run_id: str) -> str:
        job = await asyncio.to_thread(queue.claim, worker_id)
        if job is None:
            return IDLE
        task = asyncio.create_task(
            asyncio.to_thread(process, queue, job, resolve_access, run=engine)
        )
        while not task.done():
            activity.heartbeat(job.run_id)
            await asyncio.wait({task}, timeout=10)
        return (await task).value

    return run_analysis_activity


def make_workflow() -> Any:
    """The workflow class: one activity, retried, with a heartbeat timeout."""
    _, workflow = _require()
    from temporalio.common import RetryPolicy

    @workflow.defn(name=WORKFLOW_NAME)
    class AnalysisWorkflow:
        @workflow.run
        async def run(self, run_id: str) -> str:
            return await workflow.execute_activity(
                ACTIVITY_NAME,
                run_id,
                start_to_close_timeout=timedelta(hours=2),
                heartbeat_timeout=timedelta(seconds=60),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )

    return AnalysisWorkflow


async def build_worker(
    client: Any, queue: JobQueue, resolve_access: ResolveAccess, **kwargs: Any
) -> Any:
    """A ``temporalio.worker.Worker`` serving the workflow and activity on ``TASK_QUEUE``."""
    _require()
    from temporalio.worker import Worker

    return Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[make_workflow()],
        activities=[make_activity(queue, resolve_access, **kwargs)],
    )


async def start_analysis(client: Any, run_id: str) -> Any:
    """Start the workflow for a submitted run; the workflow id is the run id."""
    _require()
    return await client.start_workflow(WORKFLOW_NAME, run_id, id=run_id, task_queue=TASK_QUEUE)
