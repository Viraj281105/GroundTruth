"""Endpoints for jobs: submit an analysis, poll its status and progress, cancel it.

**Owner: Bhumi.**

Polling, not streaming: the state lives in the database, so a client asks for it. A
Kariba run takes seconds, so once a second is enough, and polling works through any proxy
without long-held connections. The response says when to stop (``terminal``).

Every endpoint needs a session and is authorized through the project the job is filed
under. Reading a job needs access to the project; submitting or cancelling needs the
organization role that may start runs *and* ownership of the project (a grant never lets a
tenant start or cancel a run). A job with no project is not found by anyone. Both writes are
audited (``run.start``, ``run.cancel``) and a new run records who asked (``requested_by``).

A refusal is a completed job: ``succeeded`` with ``result_state: "refused"``. Results and
history are served by ``/runs``; this module is the lightweight thing a UI polls.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response

from groundtruth.contracts.errors import CaseDefinitionError
from groundtruth.contracts.result import AnalysisStatus
from groundtruth.platform.api.dependencies import get_jobs, store_errors
from groundtruth.platform.api.errors import (
    ApiErrorBody,
    ApiErrorCode,
    api_error,
    case_validation_error,
)
from groundtruth.platform.api.rate_limits import spend_submission
from groundtruth.platform.api.schemas import JobSubmission, JobView, SubmitJobRequest
from groundtruth.platform.api.scope import audit, authorize_case, authorize_filed
from groundtruth.platform.auth.authz import Action, Capability, Context
from groundtruth.platform.auth.deps import require_role
from groundtruth.platform.cases.registry import CaseValidationError, get_case
from groundtruth.platform.config import get_settings
from groundtruth.platform.jobs.interface import JobControl
from groundtruth.platform.jobs.lifecycle import IllegalTransitionError, JobNotFoundError
from groundtruth.platform.metrics import record_cache

router = APIRouter(prefix="/jobs", tags=["jobs"])

Jobs = Annotated[JobControl, Depends(get_jobs)]

_NO_STORE = "no-store"
"""A status that is cached is a status that is wrong. Polling must always reach the server."""

_UNAVAILABLE: dict[int | str, dict[str, Any]] = {
    401: {"model": ApiErrorBody, "description": "Not signed in."},
    403: {"model": ApiErrorBody, "description": "Your role or access level does not allow this."},
    503: {"model": ApiErrorBody, "description": "The job store is not available."},
}


def _not_found(run_id: str):  # type: ignore[no-untyped-def]
    return api_error(ApiErrorCode.RUN_NOT_FOUND, f"No job {run_id!r}.")


@router.post(
    "",
    response_model=JobSubmission,
    status_code=202,
    summary="Queue an analysis",
    dependencies=[Depends(require_role("user"))],
    responses={
        200: {"model": JobSubmission, "description": "An existing result or job answers it."},
        404: {"model": ApiErrorBody, "description": "Unknown case, or no access to its project."},
        422: {
            "description": "The body is invalid (a validation error), or `min_donors` is below "
            "the case's floor (`min_donors_below_case_floor`).",
            "content": {
                "application/json": {
                    "schema": {
                        "anyOf": [
                            {"$ref": "#/components/schemas/HTTPValidationError"},
                            {"$ref": "#/components/schemas/ApiErrorBody"},
                        ]
                    }
                }
            },
        },
        429: {
            "model": ApiErrorBody,
            "description": "Over the per-user analysis submission limit "
            "(`too_many_submissions`, shared with `/verify`). See `Retry-After`.",
        },
        501: {"model": ApiErrorBody, "description": "Observed data is not implemented."},
        **_UNAVAILABLE,
    },
)
def submit_job(
    body: SubmitJobRequest, response: Response, jobs: Jobs, request: Request, ctx: Context
) -> JobSubmission:
    """Queue a simulated analysis for a case and return at once; poll `status_url`.

    * **`202`**: a new job was queued.
    * **`200`**: nothing new was queued. Either a stored result already answers this exact
      request (`from_cache`), or an identical job is already in flight (`deduplicated`).
      `run_id` is that existing run.

    Only simulated data can run, and the response says so (`is_simulated`, `notice`).
    `synthetic: false` is refused with `501`; it is never quietly simulated. There is no
    `true_effect` field: it is not part of the specification hash, so accepting it would
    let two different simulations share one cached answer.

    The case must belong to a project the caller's organization owns, and the caller's role
    must allow starting runs; the run is recorded with the caller as `requested_by`.
    """
    access = authorize_case(
        request, ctx, body.case_id, Capability.EDIT, action=Action.START_RUN, structured=True
    )
    if not body.synthetic:
        raise api_error(
            ApiErrorCode.NOT_IMPLEMENTED,
            "Observed-data analysis is not implemented: the Earth Engine reducer chain has "
            "not landed.",
            hint="Submit with synthetic=true to queue a simulated run.",
        )
    try:
        case = get_case(body.case_id)
    except CaseDefinitionError as exc:
        raise api_error(ApiErrorCode.CASE_NOT_FOUND, str(exc)) from exc

    try:
        min_donors = case.resolve_min_donors(body.min_donors)
    except CaseValidationError as exc:
        raise case_validation_error(exc) from exc
    analysis_request = case.to_request(
        data_mode="simulated", seed=get_settings().random_seed, min_donors=min_donors
    )
    spend_submission(
        request, user_id=ctx.user_id, organization_id=ctx.org_id, path="job", case_id=body.case_id
    )
    with store_errors():
        submission = jobs.submit(
            case, analysis_request, requested_by=ctx.user_id, project_id=access.project.id
        )
        job = jobs.status(submission.run_id)
    assert job is not None  # it was just created, or found
    record_cache("result", hit=submission.from_cache)
    audit(
        request,
        ctx,
        action="run.start",
        resource_type="run",
        resource_id=submission.run_id,
        details={
            "project_id": access.project.id,
            "case_id": body.case_id,
            "from_cache": str(submission.from_cache).lower(),
            "deduplicated": str(submission.deduplicated).lower(),
        },
    )
    if submission.from_cache or submission.deduplicated:
        response.status_code = 200
    response.headers["Cache-Control"] = _NO_STORE
    return JobSubmission(
        run_id=submission.run_id,
        from_cache=submission.from_cache,
        deduplicated=submission.deduplicated,
        status_url=f"/jobs/{submission.run_id}",
        job=JobView.build(job),
    )


@router.get(
    "/{run_id}",
    response_model=JobView,
    summary="A job's status and progress",
    responses={
        404: {"model": ApiErrorBody, "description": "No such job, or no access to its project."},
        **_UNAVAILABLE,
    },
)
def get_job(run_id: str, response: Response, jobs: Jobs, request: Request, ctx: Context) -> JobView:
    """Where a job is, cheap enough to poll about once a second until `terminal` is true.

    `stages` are what was observed as the job moved through the worker: claim, data access,
    the engine, recording. The engine is one uninterruptible step, so its internal timings
    (`engine_metrics`) appear only after it finishes, and there is **no percentage** at any
    point. While the engine runs you get its `elapsed_ms`, which is time spent, not
    progress. A **refusal** is `succeeded` with `result_state: "refused"`: the job worked.
    """
    response.headers["Cache-Control"] = _NO_STORE
    with store_errors():
        job = jobs.status(run_id)
    authorize_filed(
        request,
        ctx,
        job.project_id if job is not None else None,
        Capability.OVERVIEW,
        not_found=lambda: _not_found(run_id),
    )
    assert job is not None
    return JobView.build(job)


@router.post(
    "/{run_id}/cancel",
    response_model=JobView,
    summary="Cancel a job",
    dependencies=[Depends(require_role("user"))],
    responses={
        200: {"model": JobView, "description": "Cancelled (or already cancelled)."},
        202: {"model": JobView, "description": "Running: cancel requested, not yet honoured."},
        404: {"model": ApiErrorBody, "description": "No such job, or no access to its project."},
        409: {"model": ApiErrorBody, "description": "Already finished; nothing to cancel."},
        **_UNAVAILABLE,
    },
)
def cancel_job(
    run_id: str, response: Response, jobs: Jobs, request: Request, ctx: Context
) -> JobView:
    """Stop a job.

    * **queued** → `200`, `cancelled` at once; no worker will start it.
    * **running** → `202`, still `running` with `cancel_requested: true`. The engine is one
      uninterruptible step, so the worker honours the request when it reaches a checkpoint
      or the engine returns; the result is then discarded and the job ends `cancelled`.
    * **already cancelled**, or cancel already requested → the same answer again.
    * **succeeded or failed** → `409 job_already_finished`; nothing changes.
    """
    response.headers["Cache-Control"] = _NO_STORE
    with store_errors():
        current = jobs.status(run_id)
    access = authorize_filed(
        request,
        ctx,
        current.project_id if current is not None else None,
        Capability.EDIT,
        action=Action.START_RUN,
        not_found=lambda: _not_found(run_id),
    )
    with store_errors():
        try:
            outcome = jobs.cancel(run_id)
        except JobNotFoundError as exc:
            raise _not_found(run_id) from exc
        except IllegalTransitionError as exc:
            raise api_error(
                ApiErrorCode.JOB_ALREADY_FINISHED,
                f"Job {run_id!r} already {exc.current.value}, so there is nothing to cancel.",
            ) from exc
        job = jobs.status(run_id)
    assert job is not None
    audit(
        request,
        ctx,
        action="run.cancel",
        resource_type="run",
        resource_id=run_id,
        details={"project_id": access.project.id, "outcome": outcome.value},
    )
    if outcome is AnalysisStatus.RUNNING:
        response.status_code = 202
    return JobView.build(job)
