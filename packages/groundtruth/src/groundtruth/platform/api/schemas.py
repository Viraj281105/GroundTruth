"""Request and response schemas for the HTTP API.

The API deliberately exposes the evidence bundle rather than a bare verdict. A
consumer that only wants the label can read one field; a consumer doing due
diligence gets the full provenance in the same response.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from groundtruth.contracts.evidence import EvidenceBundle
from groundtruth.contracts.identifiers import DatasetRef
from groundtruth.contracts.result import (
    AnalysisError,
    AnalysisResult,
    AnalysisStatus,
    ErrorCode,
    RunMetrics,
)
from groundtruth.contracts.types import VerdictLabel
from groundtruth.platform.compare.comparison import Comparison, NotComparable
from groundtruth.platform.compare.diff import BundleDiff
from groundtruth.platform.jobs.interface import LIVE_STAGES, JobStatus
from groundtruth.platform.reports.narrative import generate_report
from groundtruth.platform.store.interface import ResultState, RunSummary


class HealthResponse(BaseModel):
    """Service liveness and capability report."""

    status: str = "ok"
    version: str
    engine_version: str = ""
    contract_version: str = ""
    engine_capabilities: dict[str, bool] = Field(
        default_factory=dict,
        description="What the engine can actually do, reported by the engine itself.",
    )
    earth_observation_implemented: bool = Field(
        default=False, description="False until the Earth Engine reducer chain lands."
    )
    genai_narration_implemented: bool = Field(
        default=False, description="False until a narration provider is implemented."
    )
    cases_available: int = 0


class CaseSummary(BaseModel):
    """A case as listed by the API."""

    case_id: str
    name: str
    country: str
    standard: str
    registry_id: str | None = None
    ecosystem: str
    indicator: str
    pre_period: str
    post_period: str
    status: str
    has_known_reference: bool


class CaseDetail(CaseSummary):
    """Full case definition, including validation references."""

    area_ha: float | None = None
    donor_search_region: str
    donor_pool_size: int
    covariates: list[str]
    known_reference: dict[str, Any] = Field(
        default_factory=dict,
        description="Published third-party findings. Never an input to the estimate.",
    )
    notes: str = ""


class CreateCaseRequest(BaseModel):
    """Request to define and register a new project case."""

    name: str = Field(min_length=2, max_length=120)
    country: str = Field(min_length=2, max_length=80)
    ecosystem: str = Field(default="forest / woodland")
    standard: str = Field(default="VCS")
    registry_id: str = Field(min_length=2, max_length=60)
    area_ha: float = Field(gt=0)
    crediting_period_start: str = Field(default="2015-01-01")
    crediting_period_end: str = Field(default="2045-12-31")
    claimed_credits_tco2e: float | None = None
    indicator: str = Field(default="ndvi")
    donor_pool_size: int = Field(default=50, ge=10, le=100)
    pre_start: int = Field(default=2005)
    pre_end: int = Field(default=2014)
    post_start: int = Field(default=2015)
    post_end: int = Field(default=2022)
    boundary_geojson: dict[str, Any] | None = None
    case_id: str | None = None
    status: str | None = Field(
        default=None,
        description=(
            "Not settable. Cases created here are always 'scaffolded'; omit this field. "
            "Sending 'analysed' is refused with `case_status_requires_review`, because that "
            "status needs a run reviewed by both owners (C7, #4), and any other value is "
            "refused with `invalid_case`."
        ),
    )


class DataSourceMode(StrEnum):
    """Execution mode: synthetic benchmark vs genuine real observations."""

    REAL_OBSERVATIONS = "REAL_OBSERVATIONS"
    SYNTHETIC_BENCHMARK = "SYNTHETIC_BENCHMARK"


class VerificationRequest(BaseModel):
    """Options for a verification run."""

    synthetic: bool = Field(
        default=True,
        description=(
            "Must be true until real Earth-observation providers are implemented. A request "
            "with synthetic=false is rejected rather than silently simulated."
        ),
    )
    data_mode: DataSourceMode | str | None = Field(
        default=None,
        description=(
            "Explicit data mode: 'REAL_OBSERVATIONS' or 'SYNTHETIC_BENCHMARK'. "
            "Takes precedence over 'synthetic' if specified."
        ),
    )
    true_effect: float = Field(
        default=0.06, description="Effect injected into the simulated treated unit."
    )
    min_donors: int | None = Field(
        default=None,
        ge=2,
        description=(
            "Omit to use the case's own floor. A larger value makes the run stricter; a "
            "value below the case's floor is refused with `min_donors_below_case_floor`."
        ),
    )
    include_report: bool = True


class VerificationResponse(BaseModel):
    """The result of a verification run."""

    run_id: str
    case_id: str
    spec_hash: str = Field(
        description="Hash of the analysis specification. Identical hashes must yield "
        "identical results under the same engine version."
    )
    engine_version: str
    contract_version: str
    duration_ms: float = 0.0
    data_mode: Literal["simulated", "observed"] = Field(
        description="Drives the persistent simulated-data / real-observations banner."
    )
    verdict_label: VerdictLabel
    verdict_rationale: str
    caveats: list[str]
    warnings: list[str]
    bundle: EvidenceBundle
    report_markdown: str | None = None
    report_generator: str | None = None


class MessageErrorBody(BaseModel):
    """An error whose ``detail`` is a plain message, e.g. an unknown case (404)."""

    detail: str


class EngineFailureDetail(BaseModel):
    """Why ``/verify`` returned no result: the engine refused, or could not run.

    ``is_refusal`` is the field that matters. A refusal is the system correctly declining
    to produce a fragile number, and is shown as a legitimate outcome, not as an error.
    """

    code: ErrorCode
    message: str
    stage: str
    is_refusal: bool
    remediation: str | None
    run_id: str


class EngineFailureBody(BaseModel):
    """The body ``/verify`` returns when the engine refused or could not run."""

    detail: EngineFailureDetail


class ErrorResponse(BaseModel):
    """A structured error."""

    error: str
    detail: str
    hint: str | None = None


# --- stored runs: list, get, compare (issue #35) ---------------------------------------

SIMULATED_NOTICE = (
    "SIMULATED DATA: this run used the synthetic fixture provider. Its numbers describe a "
    "test fixture and say nothing about any real project."
)
"""Sent with every simulated run, so no consumer has to remember to add it (R7)."""


def _is_refusal(error_code: str | None) -> bool | None:
    if error_code is None:
        return None
    try:
        return ErrorCode(error_code).is_refusal
    except ValueError:  # a code added in a later minor contract: not known to be a refusal
        return False


class RunItem(BaseModel):
    """One stored run, as a list or a comparison shows it.

    ``status`` is the job; ``result_state`` is what happened to the analysis, in the
    UI's existing vocabulary. A **refused** run is a successful job (``status`` is
    ``succeeded``) whose ``result_state`` is ``refused``: a legitimate outcome to
    display, never an error. ``is_simulated`` and ``data_mode`` are always present.
    """

    run_id: str
    case_id: str
    spec_hash: str
    status: str = Field(description="Job lifecycle: queued, running, succeeded, failed, cancelled.")
    result_state: ResultState = Field(
        description="queued | running | measured | refused | failed | cancelled."
    )
    engine_status: str | None = Field(
        description="completed | refused | error, once the engine ran."
    )
    verdict_label: str | None
    data_mode: str = Field(description="'simulated' or 'observed'.")
    is_simulated: bool = Field(description="True for simulated data. Drives the UI banner.")
    notice: str | None = Field(description="Plain-language simulated-data notice, when simulated.")
    engine_version: str | None
    contract_version: str
    created_at: datetime = Field(description="When the run was recorded (UTC); the sort key.")
    error_code: str | None = None
    is_refusal: bool | None = Field(
        default=None, description="Set when the run has a stored error: true for a refusal."
    )
    failure_reason: str | None = Field(
        default=None, description="Why a run failed before the engine produced an error."
    )

    @classmethod
    def from_summary(cls, summary: RunSummary) -> RunItem:
        return cls(
            run_id=summary.run_id,
            case_id=summary.case_id,
            spec_hash=summary.spec_hash,
            status=summary.status,
            result_state=summary.result_state,
            engine_status=summary.engine_status,
            verdict_label=summary.verdict_label,
            data_mode=summary.data_mode,
            is_simulated=summary.is_simulated,
            notice=SIMULATED_NOTICE if summary.is_simulated else None,
            engine_version=summary.engine_version,
            contract_version=summary.contract_version,
            created_at=summary.created_at,
            error_code=summary.error_code,
            is_refusal=_is_refusal(summary.error_code),
            failure_reason=summary.failure_reason,
        )


class RunListPage(BaseModel):
    """A page of runs, newest first."""

    items: list[RunItem]
    next_cursor: str | None = Field(
        description="Pass as `cursor` to get the next page. Null on the last page."
    )
    limit: int
    contains_simulated: bool = Field(description="True if any run on this page is simulated.")


class RunError(BaseModel):
    """A stored analysis error. A refusal has ``is_refusal`` true and is not a fault."""

    code: str
    message: str
    stage: str
    detail: dict[str, Any]
    remediation: str | None
    is_refusal: bool

    @classmethod
    def from_error(cls, error: AnalysisError) -> RunError:
        return cls(
            code=error.code.value,
            message=error.message,
            stage=error.stage,
            detail=error.detail,
            remediation=error.remediation,
            is_refusal=error.is_refusal,
        )


class RunEngine(BaseModel):
    engine_version: str
    contract_version: str
    git_sha: str | None


class RunDetail(RunItem):
    """One stored run in full: its lifecycle, its outcome, and its evidence bundle."""

    has_bundle: bool = Field(description="False for a refused, failed, queued or cancelled run.")
    engine: RunEngine | None = None
    seed: int | None = None
    datasets: list[DatasetRef] = Field(default_factory=list)
    started_at: str | None = None
    finished_at: str | None = None
    metrics: RunMetrics | None = None
    error: RunError | None = Field(
        default=None, description="Present for a refused run or an engine error."
    )
    verdict_rationale: str | None = None
    caveats: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    bundle: EvidenceBundle | None = Field(
        default=None, description="Null when excluded with include_bundle=false, or absent."
    )
    report_markdown: str | None = Field(
        default=None,
        description="Deterministic report, when asked for with include_report=true and the "
        "run has a bundle with a verdict. Rendered on read; never narrated by a model.",
    )
    report_generator: str | None = None

    @classmethod
    def build(
        cls,
        summary: RunSummary,
        result: AnalysisResult | None,
        *,
        include_bundle: bool,
        include_report: bool = False,
    ) -> RunDetail:
        item = RunItem.from_summary(summary)
        bundle = result.bundle if result else None
        verdict = bundle.verdict if bundle else None
        # The deterministic renderer only: a stored run is read back, not re-narrated (R4).
        report = generate_report(bundle) if include_report and bundle and verdict else None
        return cls(
            **item.model_dump(),
            has_bundle=bundle is not None,
            engine=(
                RunEngine(
                    engine_version=result.engine.engine_version,
                    contract_version=result.engine.contract_version,
                    git_sha=result.engine.git_sha,
                )
                if result
                else None
            ),
            seed=result.seed if result else None,
            datasets=list(result.datasets) if result else [],
            started_at=result.started_at if result else None,
            finished_at=result.finished_at if result else None,
            metrics=result.metrics if result else None,
            error=RunError.from_error(result.error) if result and result.error else None,
            verdict_rationale=verdict.rationale if verdict else None,
            caveats=list(verdict.caveats) if verdict else [],
            warnings=list(bundle.warnings) if bundle else [],
            bundle=bundle if include_bundle else None,
            report_markdown=report.markdown if report else None,
            report_generator=report.generator if report else None,
        )


class RunComparison(BaseModel):
    """Two runs compared by evidence id, or the reasons they cannot be.

    ``comparable: false`` means NOT COMPARABLE: ``diff`` is null and no difference is
    presented, because across engine versions, data modes or cases a difference in a
    number may be an artefact of the instrument and not a change in the project.
    """

    baseline: RunItem
    candidate: RunItem
    comparable: bool
    not_comparable: list[NotComparable] = Field(
        description="Every reason the pair cannot be compared; empty when comparable."
    )
    same_specification: bool = Field(
        description="False when the two runs were requested with different specifications "
        "(inputs, window, seed, or pinned datasets). Still comparable; read the diff knowing it."
    )
    contains_simulated: bool
    diff: BundleDiff | None = None

    @classmethod
    def build(
        cls, baseline: RunSummary, candidate: RunSummary, outcome: Comparison
    ) -> RunComparison:
        return cls(
            baseline=RunItem.from_summary(baseline),
            candidate=RunItem.from_summary(candidate),
            comparable=outcome.comparable,
            not_comparable=list(outcome.not_comparable),
            same_specification=outcome.same_specification,
            contains_simulated=baseline.is_simulated or candidate.is_simulated,
            diff=outcome.diff,
        )


# --- jobs: status, progress, cancel, submit (issue #37) --------------------------------

STAGE_LABELS: dict[str, str] = {
    "claim": "Claimed by a worker",
    "data": "Resolving data access",
    "engine": "Running the analysis engine",
    "record": "Recording the result",
}
"""Display names for the live stages. The UI may use its own; the keys are the contract."""

INSTANT_STAGES = frozenset({"record"})
"""Stages that begin and end in one database transaction. No duration is claimed for them:
the start and end times are the same instant, and a duration of zero would be false."""

PROGRESS_NOTE = (
    "There is no percentage because none can be known: the analysis engine runs as one step "
    "and reports its internal timings only when it finishes. `stages` are observed as they "
    "happen; `engine_metrics` fills in afterwards."
)

StageState = Literal["done", "active", "pending", "skipped", "failed", "unknown"]


class StageView(BaseModel):
    """One live stage of a job, as it was observed."""

    name: str
    label: str
    state: StageState = Field(
        description="done | active | pending | skipped (never reached) | failed | unknown "
        "(no stage was recorded for this job)."
    )
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: float | None = Field(default=None, description="Finished stages only.")
    elapsed_ms: float | None = Field(
        default=None,
        description="Time spent in the active stage so far. A clock reading, not a fraction "
        "of anything.",
    )


class EngineStageTiming(BaseModel):
    name: str
    duration_ms: float


class EngineMetricsView(BaseModel):
    """The engine's own timings, taken from ``RunMetrics``. Present only after it returns."""

    available: bool
    source: Literal["run_metrics"] = "run_metrics"
    total_ms: float | None = None
    stages: list[EngineStageTiming] = Field(
        default_factory=list,
        description="The engine's internal stages and how long each took, in order. The "
        "engine reports these only for a completed analysis; a refusal or error has none.",
    )
    stopped_at: str | None = Field(
        default=None, description="The stage a refusal or error came from, as the engine names it."
    )
    n_units_observed: int | None = None
    n_donors_admitted: int | None = None
    n_estimator_fits: int | None = None
    note: str


class TimelineEvent(BaseModel):
    event: str = Field(description="queued | running | succeeded | failed | cancelled")
    at: datetime


def _ms(delta_seconds: float) -> float:
    return max(0.0, delta_seconds * 1000.0)


def _stage_views(job: JobStatus) -> list[StageView]:
    """The live stages, from what the worker recorded and nothing else."""
    log = job.stage_log
    terminal = job.terminal
    logged = [name for name in LIVE_STAGES if name in log]
    failed_in = (
        logged[-1]
        if logged and job.status is AnalysisStatus.FAILED and job.engine_status is None
        else None
    )
    views: list[StageView] = []
    for i, name in enumerate(LIVE_STAGES):
        label = STAGE_LABELS[name]
        if name not in log:
            if log or job.status is AnalysisStatus.QUEUED:
                state: StageState = "skipped" if terminal else "pending"
            elif job.attempts == 0:
                state = "skipped" if terminal else "pending"  # never taken by a worker
            else:
                state = "unknown"  # a job with no recorded stages (older, or saved directly)
            views.append(StageView(name=name, label=label, state=state))
            continue
        started = log[name]
        later = [log[n] for n in LIVE_STAGES[i + 1 :] if n in log]
        finished = min(later) if later else (job.updated_at if terminal else None)
        if finished is None:
            views.append(
                StageView(
                    name=name,
                    label=label,
                    state="active",
                    started_at=started,
                    elapsed_ms=_ms((job.as_of - started).total_seconds()),
                )
            )
            continue
        duration = None if name in INSTANT_STAGES else _ms((finished - started).total_seconds())
        views.append(
            StageView(
                name=name,
                label=label,
                state="failed" if name == failed_in else "done",
                started_at=started,
                finished_at=finished,
                duration_ms=duration,
            )
        )
    return views


def _engine_metrics(job: JobStatus) -> EngineMetricsView:
    metrics = job.metrics
    if metrics is None or job.engine_status is None:
        return EngineMetricsView(
            available=False, note="Available when the engine finishes. Nothing is estimated."
        )
    stages = [
        EngineStageTiming(name=name, duration_ms=ms)
        for name, ms in metrics.stage_durations_ms.items()
    ]
    return EngineMetricsView(
        available=True,
        total_ms=metrics.duration_ms,
        stages=stages,
        stopped_at=job.error.stage if job.error else None,
        n_units_observed=metrics.n_units_observed,
        n_donors_admitted=metrics.n_donors_admitted,
        n_estimator_fits=metrics.n_estimator_fits,
        note=(
            "From RunMetrics, recorded by the engine when it returned."
            if stages
            else "The engine reports per-stage timings only for a completed analysis. For this "
            "run it reported its total time and counts, and where it stopped."
        ),
    )


class JobView(BaseModel):
    """A job's status and progress, small enough to poll every second.

    A **refusal** is a completed job: ``status`` is ``succeeded``, ``result_state`` is
    ``refused``, ``terminal`` is true and ``error.is_refusal`` is true. It is never
    ``failed``. ``is_simulated`` and ``data_mode`` are always present, and a simulated job
    carries a ``notice``.
    """

    run_id: str
    case_id: str
    status: str = Field(description="queued | running | succeeded | failed | cancelled")
    result_state: ResultState
    terminal: bool = Field(description="True once nothing more will happen; stop polling.")
    engine_status: str | None
    data_mode: str
    is_simulated: bool
    notice: str | None
    attempt: int | None = Field(description="How many times a worker has taken the job.")
    max_attempts: int | None
    cancel_requested: bool = Field(
        description="True once a cancel was requested. A running job honours it when its "
        "worker reaches a checkpoint or the engine returns."
    )
    stage: str | None = Field(description="The live stage in progress, if one is recorded.")
    stages: list[StageView]
    engine_metrics: EngineMetricsView
    timeline: list[TimelineEvent]
    created_at: datetime
    updated_at: datetime | None
    last_heartbeat_at: datetime | None = Field(
        description="When the worker last renewed its lease. Coarse: about a third of the lease."
    )
    lease_expires_at: datetime | None
    retry_at: datetime | None = Field(
        description="When a job waiting to retry becomes available again."
    )
    error: RunError | None = Field(
        description="A refusal (is_refusal true) or an engine error, once recorded."
    )
    failure_reason: str | None
    status_url: str
    result_url: str | None = Field(description="Where the stored result is, once there is one.")
    note: str = PROGRESS_NOTE

    @classmethod
    def build(cls, job: JobStatus) -> JobView:
        timeline = [TimelineEvent(event="queued", at=job.created_at)]
        if "claim" in job.stage_log:
            timeline.append(TimelineEvent(event="running", at=job.stage_log["claim"]))
        if job.terminal and job.updated_at is not None:
            timeline.append(TimelineEvent(event=job.status.value, at=job.updated_at))
        return cls(
            run_id=job.run_id,
            case_id=job.case_id,
            status=job.status.value,
            result_state=job.result_state,
            terminal=job.terminal,
            engine_status=job.engine_status,
            data_mode=job.data_mode,
            is_simulated=job.is_simulated,
            notice=SIMULATED_NOTICE if job.is_simulated else None,
            attempt=job.attempts,
            max_attempts=job.max_attempts,
            cancel_requested=job.cancel_requested,
            stage=job.stage,
            stages=_stage_views(job),
            engine_metrics=_engine_metrics(job),
            timeline=timeline,
            created_at=job.created_at,
            updated_at=job.updated_at,
            last_heartbeat_at=job.heartbeat_at,
            lease_expires_at=job.lease_expires_at,
            retry_at=(
                job.available_at
                if job.status is AnalysisStatus.QUEUED and (job.attempts or 0) > 0
                else None
            ),
            error=RunError.from_error(job.error) if job.error else None,
            failure_reason=job.failure_reason,
            status_url=f"/jobs/{job.run_id}",
            result_url=f"/runs/{job.run_id}" if job.engine_status is not None else None,
        )


class SubmitJobRequest(BaseModel):
    """Queue an analysis for a case. Simulated data only, until real providers exist."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    synthetic: bool = Field(
        default=True,
        description="Must be true until real Earth-observation providers are implemented. "
        "false is refused with 501, never silently simulated.",
    )
    min_donors: int | None = Field(
        default=None,
        ge=2,
        description=(
            "Omit to use the case's own floor. A larger value makes the run stricter; a "
            "value below the case's floor is refused with `min_donors_below_case_floor`."
        ),
    )


class JobSubmission(BaseModel):
    """What submitting did: queued a new job, or pointed at an existing run."""

    run_id: str
    from_cache: bool = Field(
        description="An existing result answers this request; nothing was queued or will run."
    )
    deduplicated: bool = Field(
        description="An identical job is already queued or running; this is that job."
    )
    status_url: str
    job: JobView


OrgTypeName = Literal["ngo", "funder", "auditor", "government", "reference"]
MemberRoleName = Literal["owner", "admin", "member", "viewer"]


class OrgView(BaseModel):
    """An organization as seen by one of its members (``role`` is the caller's role)."""

    id: str
    slug: str
    name: str
    type: OrgTypeName
    role: MemberRoleName


class MemberView(BaseModel):
    user_id: str
    email: str
    role: MemberRoleName
    created_at: datetime


ProjectLevelName = Literal["owner", "audit", "contribute", "view"]
DataModeName = Literal["observed", "simulated"]


class ProjectView(BaseModel):
    """A project as seen by the active organization (``access_level`` is that org's level)."""

    id: str
    slug: str
    name: str
    country: str
    ecosystem: str
    intervention: str
    treatment_start_year: int
    data_mode: DataModeName
    owner_slug: str
    owner_name: str
    access_level: ProjectLevelName
    boundary_sha256: str | None = None
    reported_funding_amount: float | None = None
    reported_funding_currency: str | None = None
    """Reported by the owner, shown as such; never computed."""
    created_at: datetime
