"""Endpoints for stored runs: list, fetch one, and compare two.

**Owner: Bhumi.**

These read what the worker and the evidence store have recorded; they run nothing and
write nothing. The existing ``/cases/{id}/verify`` still runs an analysis inline and
stores nothing; submitting jobs through the API is a separate issue (#37).

A refused run is a legitimate outcome, so it is returned as a normal ``200`` with
``result_state: "refused"`` and its structured error, never as an HTTP error.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query

from groundtruth.contracts.result import AnalysisResult, AnalysisStatus
from groundtruth.platform.api.cursor import CursorError, decode_cursor, encode_cursor
from groundtruth.platform.api.dependencies import get_store, store_errors
from groundtruth.platform.api.errors import ApiErrorBody, ApiErrorCode, api_error
from groundtruth.platform.api.schemas import RunComparison, RunDetail, RunItem, RunListPage
from groundtruth.platform.compare.comparison import RunSide, compare_runs
from groundtruth.platform.store.interface import (
    EvidenceStore,
    IncompatibleBundleError,
    RunFilter,
    RunSummary,
)

router = APIRouter(prefix="/runs", tags=["runs"])

Store = Annotated[EvidenceStore, Depends(get_store)]

_ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"model": ApiErrorBody, "description": "No such run."},
    503: {"model": ApiErrorBody, "description": "The run store is not available."},
}


def _require_aware(value: datetime | None, name: str) -> datetime | None:
    if value is not None and value.tzinfo is None:
        raise api_error(
            ApiErrorCode.INVALID_FILTER,
            f"{name} has no timezone, so it names no instant.",
            hint="Use UTC with a trailing Z, e.g. 2026-11-01T00:00:00Z.",
        )
    # Stored times are UTC; compare like with like whatever offset the client used.
    return value.astimezone(UTC) if value is not None else None


@router.get(
    "",
    response_model=RunListPage,
    summary="List stored runs, newest first",
    responses={503: _ERRORS[503]},
)
def list_runs(
    store: Store,
    case_id: Annotated[str | None, Query(description="Only this case.")] = None,
    status: Annotated[
        list[AnalysisStatus] | None,
        Query(description="Job status; repeat to allow several. A refused run is `succeeded`."),
    ] = None,
    engine_version: Annotated[str | None, Query(description="Only this engine version.")] = None,
    data_mode: Annotated[Literal["observed", "simulated"] | None, Query()] = None,
    created_after: Annotated[
        datetime | None, Query(description="Recorded at or after this instant (timezone required).")
    ] = None,
    created_before: Annotated[
        datetime | None, Query(description="Recorded before this instant (timezone required).")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100, description="Page size.")] = 25,
    cursor: Annotated[str | None, Query(description="From a previous page's next_cursor.")] = None,
) -> RunListPage:
    """Runs matching the filters, newest first, in pages.

    Pagination is by cursor, not offset: the sort key (`created_at`, `run_id`) never
    changes, so runs written while you page cannot shift or repeat a page. A run whose
    write commits late can be missing from the scroll in progress and appears in the
    next one. There is no total count; it would be stale as soon as it was read.
    """
    after_instant = _require_aware(created_after, "created_after")
    before_instant = _require_aware(created_before, "created_before")
    if after_instant and before_instant and after_instant >= before_instant:
        raise api_error(
            ApiErrorCode.INVALID_FILTER, "created_after must be earlier than created_before."
        )
    filters = RunFilter(
        case_id=case_id,
        statuses=tuple(sorted({s.value for s in status or []})),
        engine_version=engine_version,
        data_mode=data_mode,
        created_after=after_instant,
        created_before=before_instant,
    )
    after = None
    if cursor is not None:
        try:
            after = decode_cursor(cursor, filters)
        except CursorError as exc:
            raise api_error(
                ApiErrorCode.INVALID_CURSOR,
                str(exc),
                hint="Start again without a cursor, or reuse the filters it was issued for.",
            ) from exc

    with store_errors():
        page = store.list_runs(filters, limit=limit, after=after)
    items = [RunItem.from_summary(s) for s in page.items]
    return RunListPage(
        items=items,
        next_cursor=encode_cursor(page.next_cursor, filters) if page.next_cursor else None,
        limit=limit,
        contains_simulated=any(item.is_simulated for item in items),
    )


def _load_side(store: EvidenceStore, run_id: str, role: str) -> tuple[RunSummary, RunSide]:
    summary = store.summary_for(run_id)
    if summary is None:
        raise api_error(ApiErrorCode.RUN_NOT_FOUND, f"No {role} run {run_id!r}.")
    result: AnalysisResult | None = None
    unreadable: str | None = None
    if summary.engine_status is not None:
        try:
            result = store.by_run_id(run_id)
        except IncompatibleBundleError as exc:
            unreadable = str(exc)
    return summary, RunSide(summary=summary, result=result, unreadable=unreadable)


# Declared before "/{run_id}" so the word "compare" is never taken for a run id.
@router.get(
    "/compare",
    response_model=RunComparison,
    summary="Compare two runs by evidence id",
    responses=_ERRORS,
)
def compare(
    store: Store,
    baseline: Annotated[str, Query(description="The reference run.")],
    candidate: Annotated[str, Query(description="The run to compare against it.")],
    include_unchanged: Annotated[
        bool, Query(description="List unchanged ids too (they are always counted).")
    ] = False,
) -> RunComparison:
    """A per-evidence-id diff: each id is `added`, `removed`, `changed` or `unchanged`.

    **NOT COMPARABLE.** When the runs are for different cases, differ in data mode or
    engine version, were written under incompatible contracts, or one has no evidence
    bundle (refused, failed, queued, cancelled), the response says `comparable: false`
    with every reason and returns **no diff**. A difference across engine versions is
    not presented as a change. Runs from different specifications are comparable, with
    `same_specification: false`.
    """
    with store_errors():
        baseline_summary, baseline_side = _load_side(store, baseline, "baseline")
        candidate_summary, candidate_side = _load_side(store, candidate, "candidate")
    outcome = compare_runs(baseline_side, candidate_side, include_unchanged=include_unchanged)
    return RunComparison.build(baseline_summary, candidate_summary, outcome)


@router.get(
    "/{run_id}",
    response_model=RunDetail,
    summary="Fetch one stored run",
    responses={**_ERRORS, 409: {"model": ApiErrorBody, "description": "Unreadable contract."}},
)
def get_run(
    store: Store,
    run_id: str,
    include_bundle: Annotated[
        bool, Query(description="Include the evidence bundle (it is large).")
    ] = True,
    include_report: Annotated[
        bool,
        Query(description="Render the deterministic report from the bundle, when there is one."),
    ] = False,
) -> RunDetail:
    """One run with its outcome and, when it has one, its evidence bundle.

    A refused run returns `200` with `result_state: "refused"` and the structured
    error (code, stage, message, remediation, detail). A run still queued or running
    returns its state with no bundle.

    With `include_report=true` a run that has a bundle also carries `report_markdown`,
    rendered on read by the deterministic renderer. No language model narrates a
    stored run.
    """
    with store_errors():
        summary = store.summary_for(run_id)
        if summary is None:
            raise api_error(ApiErrorCode.RUN_NOT_FOUND, f"No run {run_id!r}.")
        result = store.by_run_id(run_id) if summary.engine_status is not None else None
    return RunDetail.build(
        summary, result, include_bundle=include_bundle, include_report=include_report
    )
