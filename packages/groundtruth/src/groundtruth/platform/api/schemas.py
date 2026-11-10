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
from groundtruth.platform.api.error_envelope import scrub_optional, scrub_text
from groundtruth.platform.compare.comparison import Comparison, NotComparable
from groundtruth.platform.compare.diff import BundleDiff
from groundtruth.platform.jobs.interface import LIVE_STAGES, JobStatus
from groundtruth.platform.reports.narrative import generate_report
from groundtruth.platform.store.interface import ResultState, RunSummary


class HealthResponse(BaseModel):
    """Service liveness and capability report."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    status: str = "ok"
    """Always `ok` when the API answers; a failing service answers an error instead."""
    version: str
    """The GroundTruth package version serving this API."""
    engine_version: str = ""
    """Version of the analysis engine every new run uses."""
    contract_version: str = ""
    """Version of the engine contract; results record the one they used."""
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
    """How many case definitions this deployment has loaded."""


class CaseSummary(BaseModel):
    """A case as listed by the API."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    case_id: str
    """Stable identifier of the case, used in every case and run URL."""
    name: str
    """Human-readable project name."""
    country: str
    """Country the project lies in."""
    standard: str
    """Certification standard the project reports under, e.g. `VCS`."""
    registry_id: str | None = None
    """The project's identifier in its registry, when known."""
    ecosystem: str
    """Ecosystem type, e.g. `forest / woodland`."""
    indicator: str
    """Vegetation index the analysis measures, e.g. `ndvi`. An index, never carbon."""
    pre_period: str
    """Pre-treatment years used to fit the comparison, as `start-end`."""
    post_period: str
    """Post-treatment years in which the effect is measured, as `start-end`."""
    status: str
    """Case lifecycle status. New cases are `scaffolded`; only a case with a run reviewed by both
    owners may be `analysed`."""
    has_known_reference: bool
    """True if published third-party findings exist to compare against. They are never an input to
    the estimate."""


class CaseDetail(CaseSummary):
    """Full case definition, including validation references."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    area_ha: float | None = None
    """Project area in hectares, as declared by the case."""
    donor_search_region: str
    """Where comparison (donor) areas are searched for."""
    donor_pool_size: int
    """How many candidate donor areas the search draws before screening."""
    covariates: list[str]
    """Variables used to match donors to the project area."""
    known_reference: dict[str, Any] = Field(
        default_factory=dict,
        description="Published third-party findings. Never an input to the estimate.",
    )
    notes: str = ""
    """Free-text notes from the case definition."""


class CreateCaseRequest(BaseModel):
    """Request to define and register a new project case."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    name: str = Field(min_length=2, max_length=120)
    """Project name, 2 to 120 characters. The case id is derived from it unless `case_id` is given."""
    country: str = Field(min_length=2, max_length=80)
    """Country the project lies in, 2 to 80 characters."""
    ecosystem: str = Field(default="forest / woodland")
    """Ecosystem type."""
    standard: str = Field(default="VCS")
    """Certification standard, e.g. `VCS`."""
    registry_id: str = Field(min_length=2, max_length=60)
    """The project's registry identifier, 2 to 60 characters."""
    area_ha: float = Field(gt=0)
    """Declared project area in hectares; must be positive."""
    crediting_period_start: str = Field(default="2015-01-01")
    """First day of the crediting period, `YYYY-MM-DD`."""
    crediting_period_end: str = Field(default="2045-12-31")
    """Last day of the crediting period, `YYYY-MM-DD`."""
    claimed_credits_tco2e: float | None = None
    """Credits the developer claims, in tCO2e, if known. Shown beside the evidence, never used to
    compute it."""
    indicator: str = Field(default="ndvi")
    """Vegetation index to measure: `ndvi`, `evi`, `ndmi` or `nbr`."""
    donor_pool_size: int = Field(default=50, ge=10, le=100)
    """Candidate donor areas to draw, 10 to 100."""
    pre_start: int = Field(default=2005)
    """First pre-treatment year."""
    pre_end: int = Field(default=2014)
    """Last pre-treatment year; must come before `post_start`."""
    post_start: int = Field(default=2015)
    """First post-treatment year (the intervention year)."""
    post_end: int = Field(default=2022)
    """Last post-treatment year."""
    boundary_geojson: dict[str, Any] | None = None
    """Project boundary as GeoJSON. Optional; validated before anything is written."""
    case_id: str | None = None
    """Choose the case id instead of deriving it from `name`. Must be unique."""
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

    model_config = ConfigDict(use_attribute_docstrings=True)

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
    """Also return a plain-language report of the result (`report_markdown`)."""


class VerificationResponse(BaseModel):
    """The result of a verification run."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    run_id: str
    """Identifier of this run."""
    case_id: str
    """The case that was analysed."""
    spec_hash: str = Field(
        description="Hash of the analysis specification. Identical hashes must yield "
        "identical results under the same engine version."
    )
    engine_version: str
    """Engine version that produced the result."""
    contract_version: str
    """Engine contract version of the result."""
    duration_ms: float = 0.0
    """How long the engine took, in milliseconds."""
    data_mode: Literal["simulated", "observed"] = Field(
        description="Drives the persistent simulated-data / real-observations banner."
    )
    verdict_label: VerdictLabel
    """The screening verdict. A divergence warrants accredited review; it is never a finding of
    fraud."""
    verdict_rationale: str
    """Why the engine reached this verdict, in its own words, thresholds included."""
    caveats: list[str]
    """Statements that must accompany the verdict wherever it is shown."""
    warnings: list[str]
    """Analyst-facing warnings, e.g. that the data is simulated."""
    bundle: EvidenceBundle
    """The evidence bundle: every measured value with its unit, uncertainty and provenance."""
    report_markdown: str | None = None
    """Plain-language report, when `include_report` was true."""
    report_generator: str | None = None
    """Who wrote `report_markdown`: `deterministic`, or `genai:<provider>` when narrated."""


class MessageErrorBody(BaseModel):
    """An error whose ``detail`` is a plain message, e.g. an unknown case (404).

    ``code`` (``http_<status>``), ``is_refusal`` and ``request_id`` are added to it by the
    error envelope, so a client can read the same fields from every error.
    """

    model_config = ConfigDict(use_attribute_docstrings=True)

    detail: str
    """What went wrong, as a sentence."""
    code: str
    """Machine-readable code, `http_<status>` for this shape (e.g. `http_404`). Act on this, not on
    the prose."""
    message: str
    """The same sentence as `detail`."""
    is_refusal: bool = False
    """Always false for this shape: it is never a scientific refusal."""
    request_id: str | None = None
    """Identifier of this request, also in the `X-Request-ID` header. Quote it when reporting a
    problem."""


class EngineFailureDetail(BaseModel):
    """Why ``/verify`` returned no result: the engine refused, or could not run.

    ``is_refusal`` is the field that matters. A refusal is the system correctly declining
    to produce a fragile number, and is shown as a legitimate outcome, not as an error.
    """

    model_config = ConfigDict(use_attribute_docstrings=True)

    code: ErrorCode
    """The engine's error code. `insufficient_data` and `donor_pool_inadequate` are refusals; the
    rest are errors."""
    message: str
    """Plain-language explanation, safe to show a user."""
    stage: str
    """The engine stage that refused or failed."""
    is_refusal: bool
    """True when the engine declined to estimate because the data cannot support a reliable number.
    A legitimate outcome, not a malfunction."""
    remediation: str | None
    """What could be done about it, when the engine knows."""
    run_id: str
    """Identifier of the engine run that refused or failed."""


class EngineFailureBody(BaseModel):
    """The body ``/verify`` returns when the engine refused or could not run."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    detail: EngineFailureDetail
    """Why no result was returned."""
    is_refusal: bool = Field(
        default=False, description="The same value as `detail.is_refusal`, at the top level."
    )
    request_id: str | None = None
    """Identifier of this request, also in the `X-Request-ID` header."""


class ErrorResponse(BaseModel):
    """A structured error."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    error: str
    """Machine-readable error code."""
    detail: str
    """What went wrong."""
    hint: str | None = None
    """What to do about it, when known."""


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

    model_config = ConfigDict(use_attribute_docstrings=True)

    run_id: str
    """Identifier of the run."""
    case_id: str
    """The case the run analysed."""
    spec_hash: str
    """Hash of the analysis specification. Two runs with the same hash and engine version give the
    same numbers."""
    status: str = Field(description="Job lifecycle: queued, running, succeeded, failed, cancelled.")
    result_state: ResultState = Field(
        description="queued | running | measured | refused | failed | cancelled."
    )
    engine_status: str | None = Field(
        description="completed | refused | error, once the engine ran."
    )
    verdict_label: str | None
    """The screening verdict, once measured."""
    data_mode: str = Field(description="'simulated' or 'observed'.")
    is_simulated: bool = Field(description="True for simulated data. Drives the UI banner.")
    notice: str | None = Field(description="Plain-language simulated-data notice, when simulated.")
    engine_version: str | None
    """Engine version that produced the result, once there is one."""
    contract_version: str
    """Engine contract version of the run."""
    created_at: datetime = Field(description="When the run was recorded (UTC); the sort key.")
    error_code: str | None = None
    """The stored error's code, for a refused or errored run."""
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
            failure_reason=scrub_optional(summary.failure_reason),
        )


class RunListPage(BaseModel):
    """A page of runs, newest first."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    items: list[RunItem]
    """Runs on this page, newest first."""
    next_cursor: str | None = Field(
        description="Pass as `cursor` to get the next page. Null on the last page."
    )
    limit: int
    """The page size that was applied."""
    contains_simulated: bool = Field(description="True if any run on this page is simulated.")


class RunError(BaseModel):
    """A stored analysis error. A refusal has ``is_refusal`` true and is not a fault."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    code: str
    """Error code. `insufficient_data` and `donor_pool_inadequate` are refusals."""
    message: str
    """Plain-language explanation, safe to show a user."""
    stage: str
    """The engine stage that refused or failed."""
    detail: dict[str, Any]
    """Structured context, e.g. donors found against donors required."""
    remediation: str | None
    """What could be done about it, when known."""
    is_refusal: bool
    """True for a scientific refusal: the data could not support an estimate. Not a fault."""

    @classmethod
    def from_error(cls, error: AnalysisError) -> RunError:
        return cls(
            code=error.code.value,
            message=scrub_text(error.message),
            stage=error.stage,
            detail=error.detail,
            remediation=scrub_optional(error.remediation),
            is_refusal=error.is_refusal,
        )


class RunEngine(BaseModel):
    """The engine build that produced a run."""

    model_config = ConfigDict(use_attribute_docstrings=True)
    engine_version: str
    """Engine version."""
    contract_version: str
    """Engine contract version."""
    git_sha: str | None
    """Commit the worker ran, or null when the deployment did not record it."""


class RunDetail(RunItem):
    """One stored run in full: its lifecycle, its outcome, and its evidence bundle."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    has_bundle: bool = Field(description="False for a refused, failed, queued or cancelled run.")
    engine: RunEngine | None = None
    """The engine build that produced the run, once it ran."""
    seed: int | None = None
    """Random seed of the run. The same seed and specification reproduce the same numbers."""
    datasets: list[DatasetRef] = Field(default_factory=list)
    """Every dataset the run read, with its version."""
    started_at: str | None = None
    """When the engine started (UTC, ISO 8601)."""
    finished_at: str | None = None
    """When the engine finished (UTC, ISO 8601)."""
    metrics: RunMetrics | None = None
    """The engine's own timings and counters."""
    error: RunError | None = Field(
        default=None, description="Present for a refused run or an engine error."
    )
    verdict_rationale: str | None = None
    """Why the engine reached its verdict."""
    caveats: list[str] = Field(default_factory=list)
    """Statements that must accompany the verdict."""
    warnings: list[str] = Field(default_factory=list)
    """Analyst-facing warnings."""
    bundle: EvidenceBundle | None = Field(
        default=None, description="Null when excluded with include_bundle=false, or absent."
    )
    report_markdown: str | None = Field(
        default=None,
        description="Deterministic report, when asked for with include_report=true and the "
        "run has a bundle with a verdict. Rendered on read; never narrated by a model.",
    )
    report_generator: str | None = None
    """Who wrote `report_markdown`: `deterministic`, or `genai:<provider>`."""

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

    model_config = ConfigDict(use_attribute_docstrings=True)

    baseline: RunItem
    """The run compared against."""
    candidate: RunItem
    """The run compared with the baseline."""
    comparable: bool
    """True if the two runs can be compared item by item; see `not_comparable` otherwise."""
    not_comparable: list[NotComparable] = Field(
        description="Every reason the pair cannot be compared; empty when comparable."
    )
    same_specification: bool = Field(
        description="False when the two runs were requested with different specifications "
        "(inputs, window, seed, or pinned datasets). Still comparable; read the diff knowing it."
    )
    contains_simulated: bool
    """True if either run is simulated."""
    diff: BundleDiff | None = None
    """The item-by-item difference, when comparable."""

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

    model_config = ConfigDict(use_attribute_docstrings=True)

    name: str
    """Stage id: `claim`, `data`, `engine` or `record`."""
    label: str
    """Stage name for display."""
    state: StageState = Field(
        description="done | active | pending | skipped (never reached) | failed | unknown "
        "(no stage was recorded for this job)."
    )
    started_at: datetime | None = None
    """When the stage began."""
    finished_at: datetime | None = None
    """When the stage ended, for a finished stage."""
    duration_ms: float | None = Field(default=None, description="Finished stages only.")
    elapsed_ms: float | None = Field(
        default=None,
        description="Time spent in the active stage so far. A clock reading, not a fraction "
        "of anything.",
    )


class EngineStageTiming(BaseModel):
    """One of the engine's internal stages and how long it took."""

    model_config = ConfigDict(use_attribute_docstrings=True)
    name: str
    """The engine's name for the stage."""
    duration_ms: float
    """How long it took, in milliseconds."""


class EngineMetricsView(BaseModel):
    """The engine's own timings, taken from ``RunMetrics``. Present only after it returns."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    available: bool
    """False until the engine has returned for this job."""
    source: Literal["run_metrics"] = "run_metrics"
    """Where the timings come from: always the engine's own `RunMetrics`."""
    total_ms: float | None = None
    """Total engine time, in milliseconds."""
    stages: list[EngineStageTiming] = Field(
        default_factory=list,
        description="The engine's internal stages and how long each took, in order. The "
        "engine reports these only for a completed analysis; a refusal or error has none.",
    )
    stopped_at: str | None = Field(
        default=None, description="The stage a refusal or error came from, as the engine names it."
    )
    n_units_observed: int | None = None
    """How many areas (project and candidates) the engine observed."""
    n_donors_admitted: int | None = None
    """How many comparison areas passed screening."""
    n_estimator_fits: int | None = None
    """How many times the estimator was fitted, placebos included."""
    note: str
    """How to read these numbers."""


class TimelineEvent(BaseModel):
    """One lifecycle event of a job."""

    model_config = ConfigDict(use_attribute_docstrings=True)
    event: str = Field(description="queued | running | succeeded | failed | cancelled")
    at: datetime
    """When it happened (UTC)."""


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

    model_config = ConfigDict(use_attribute_docstrings=True)

    run_id: str
    """Identifier of the job's run."""
    case_id: str
    """The case being analysed."""
    status: str = Field(description="queued | running | succeeded | failed | cancelled")
    result_state: ResultState
    """What the run produced: queued, running, measured, refused, failed or cancelled. `refused` is
    a scientific outcome; `failed` is a fault."""
    terminal: bool = Field(description="True once nothing more will happen; stop polling.")
    engine_status: str | None
    """What the engine returned, once it ran: completed, refused or error."""
    data_mode: str
    """`simulated` or `observed`."""
    is_simulated: bool
    """True for simulated data. Show the simulated-data notice."""
    notice: str | None
    """Plain-language simulated-data notice, when simulated."""
    attempt: int | None = Field(description="How many times a worker has taken the job.")
    max_attempts: int | None
    """How many times the job may be tried before it fails for good."""
    cancel_requested: bool = Field(
        description="True once a cancel was requested. A running job honours it when its "
        "worker reaches a checkpoint or the engine returns."
    )
    stage: str | None = Field(description="The live stage in progress, if one is recorded.")
    stages: list[StageView]
    """Each live stage of the job and its state."""
    engine_metrics: EngineMetricsView
    """The engine's own timings, once it has returned."""
    timeline: list[TimelineEvent]
    """Lifecycle events, oldest first."""
    created_at: datetime
    """When the job was queued (UTC)."""
    updated_at: datetime | None
    """When the job last changed (UTC)."""
    last_heartbeat_at: datetime | None = Field(
        description="When the worker last renewed its lease. Coarse: about a third of the lease."
    )
    lease_expires_at: datetime | None
    """When the current worker's claim lapses unless renewed; the job is then retried."""
    retry_at: datetime | None = Field(
        description="When a job waiting to retry becomes available again."
    )
    error: RunError | None = Field(
        description="A refusal (is_refusal true) or an engine error, once recorded."
    )
    failure_reason: str | None
    """Why the job failed, when it failed before the engine produced an error."""
    status_url: str
    """URL to poll for this view."""
    result_url: str | None = Field(description="Where the stored result is, once there is one.")
    note: str = PROGRESS_NOTE
    """How to read the progress fields."""

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
            failure_reason=scrub_optional(job.failure_reason),
            status_url=f"/jobs/{job.run_id}",
            result_url=f"/runs/{job.run_id}" if job.engine_status is not None else None,
        )


class SubmitJobRequest(BaseModel):
    """Queue an analysis for a case. Simulated data only, until real providers exist."""

    model_config = ConfigDict(extra="forbid", use_attribute_docstrings=True)

    case_id: str
    """The case to analyse. Its project must belong to your active organization."""
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

    model_config = ConfigDict(use_attribute_docstrings=True)

    run_id: str
    """Identifier of the run that answers the request: new, cached or in flight."""
    from_cache: bool = Field(
        description="An existing result answers this request; nothing was queued or will run."
    )
    deduplicated: bool = Field(
        description="An identical job is already queued or running; this is that job."
    )
    status_url: str
    """URL to poll for the job's progress."""
    job: JobView
    """The job's current status."""


OrgTypeName = Literal["ngo", "funder", "auditor", "government", "reference"]
MemberRoleName = Literal["owner", "admin", "member", "viewer"]


class OrgView(BaseModel):
    """An organization as seen by one of its members (``role`` is the caller's role)."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    id: str
    """Organization identifier."""
    slug: str
    """Organization slug, used in URLs."""
    name: str
    """Organization name."""
    type: OrgTypeName
    """Organization type: ngo, funder, auditor, government or reference."""
    role: MemberRoleName
    """Your role in this organization: owner, admin, member or viewer."""


class MemberView(BaseModel):
    """A member of an organization."""

    model_config = ConfigDict(use_attribute_docstrings=True)
    user_id: str
    """The member's user id."""
    email: str
    """The member's email address."""
    role: MemberRoleName
    """Their role: owner, admin, member or viewer."""
    created_at: datetime
    """When they joined (UTC)."""


ProjectLevelName = Literal["owner", "audit", "contribute", "view"]
DataModeName = Literal["observed", "simulated"]


class ProjectView(BaseModel):
    """A project as seen by the active organization (``access_level`` is that org's level)."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    id: str
    """Project identifier."""
    slug: str
    """Project slug: the case id of its analysis."""
    name: str
    """Project name."""
    country: str
    """Country the project lies in."""
    ecosystem: str
    """Ecosystem type."""
    intervention: str
    """Type of intervention, e.g. REDD+ or restoration."""
    treatment_start_year: int
    """Year the intervention began."""
    data_mode: DataModeName
    """`observed` or `simulated`. Simulated data is never presented as real."""
    owner_slug: str
    """Slug of the organization that owns the project."""
    owner_name: str
    """Name of the organization that owns the project."""
    access_level: ProjectLevelName
    """Your organization's level on this project: owner, audit, contribute or view."""
    boundary_sha256: str | None = None
    """SHA-256 of the stored boundary file, when there is one."""
    reported_funding_amount: float | None = None
    """Funding as the owner reported it. Never computed by GroundTruth."""
    reported_funding_currency: str | None = None
    """Reported by the owner, shown as such; never computed."""
    created_at: datetime
    """When the project was created (UTC)."""
