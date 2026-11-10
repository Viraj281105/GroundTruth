"""Server-Sent Events for a job's per-stage progress.

The same state ``GET /jobs/{run_id}`` serves, pushed instead of polled: the server polls the
job store and emits an event whenever the view changes, then ends the stream once the job is
terminal. Like the jobs router it needs a session and access to the job's project, and the
check happens before the stream is opened: a denied caller gets a plain ``404`` (or ``403``)
and never holds a connection.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from groundtruth.platform.api.dependencies import get_jobs, store_errors
from groundtruth.platform.api.error_envelope import scrub_text
from groundtruth.platform.api.errors import ApiErrorBody, ApiErrorCode, api_error
from groundtruth.platform.api.schemas import JobView
from groundtruth.platform.api.scope import authorize_filed
from groundtruth.platform.auth.authz import Capability, Context
from groundtruth.platform.jobs.interface import JobControl

router = APIRouter(prefix="/jobs", tags=["jobs"])

Jobs = Annotated[JobControl, Depends(get_jobs)]

POLL_INTERVAL_SECONDS = 0.5
"""How often the server looks at the store for a change."""

MAX_STREAM_SECONDS = 900.0
"""A stream is closed after this long; clients reconnect. Bounds the DB polling per client."""


def _view(jobs: JobControl, job_id: str) -> JobView | None:
    with store_errors():
        job = jobs.status(job_id)
    return None if job is None else JobView.build(job)


def _project_of(jobs: JobControl, job_id: str) -> str | None:
    """The project a job is filed under (``None``: no such job, or an unfiled one)."""
    with store_errors():
        job = jobs.status(job_id)
    return None if job is None else job.project_id


def _frame(event: str, view: JobView) -> str:
    return f"event: {event}\ndata: {json.dumps(view.model_dump(mode='json'))}\n\n"


def _fingerprint(view: JobView) -> str:
    """What a client can see of progress; bare timestamp noise does not count."""
    parts: list[Any] = [view.status, view.stage, view.cancel_requested, view.attempt]
    parts.extend(s.model_dump(mode="json") for s in view.stages)
    return json.dumps(parts, sort_keys=True, default=str)


async def _stream(jobs: JobControl, job_id: str, first: JobView) -> AsyncIterator[str]:
    view = first
    last = _fingerprint(view)
    yield _frame("progress", view)
    deadline = time.monotonic() + MAX_STREAM_SECONDS
    while not view.terminal:
        if time.monotonic() > deadline:
            yield 'event: timeout\ndata: {"code": "stream_timeout"}\n\n'
            return
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
        try:
            current = await asyncio.to_thread(_view, jobs, job_id)
        except Exception as exc:
            detail = getattr(exc, "detail", None) or {"message": scrub_text(str(exc))}
            yield f"event: error\ndata: {json.dumps(detail, default=str)}\n\n"
            return
        if current is None:
            yield 'event: error\ndata: {"code": "run_not_found"}\n\n'
            return
        view = current
        fingerprint = _fingerprint(view)
        if fingerprint != last:
            last = fingerprint
            yield _frame("progress", view)
    yield _frame("done", view)


_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {
        "content": {"text/event-stream": {"schema": {"type": "string"}}},
        "description": "A stream of job events.",
    },
    401: {"model": ApiErrorBody, "description": "Not signed in."},
    404: {"model": ApiErrorBody, "description": "No such job, or no access to its project."},
    503: {"model": ApiErrorBody, "description": "The job store is not available."},
}


@router.get(
    "/{job_id}/events",
    summary="Stream a job's progress (SSE)",
    response_class=StreamingResponse,
    responses=_RESPONSES,
)
async def job_events(job_id: str, jobs: Jobs, request: Request, ctx: Context) -> StreamingResponse:
    """Emit a `progress` event with the full job view on every change, then a final `done`.

    The stream ends once the job is terminal. Unknown jobs are `404` and an unavailable
    store is `503` before any event is sent, exactly as for `GET /jobs/{run_id}`. So is a job
    in a project the caller cannot read: authorization comes first, then the stream.
    """
    project_id = await asyncio.to_thread(_project_of, jobs, job_id)
    await asyncio.to_thread(
        authorize_filed,
        request,
        ctx,
        project_id,
        Capability.OVERVIEW,
        not_found=lambda: api_error(ApiErrorCode.RUN_NOT_FOUND, f"No job {job_id!r}."),
    )
    first = await asyncio.to_thread(_view, jobs, job_id)
    if first is None:
        raise api_error(ApiErrorCode.RUN_NOT_FOUND, f"No job {job_id!r}.")
    return StreamingResponse(
        _stream(jobs, job_id, first),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
