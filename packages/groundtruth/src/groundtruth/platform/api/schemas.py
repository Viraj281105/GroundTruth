"""Request and response schemas for the HTTP API.

The API deliberately exposes the evidence bundle rather than a bare verdict. A
consumer that only wants the label can read one field; a consumer doing due
diligence gets the full provenance in the same response.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from groundtruth.contracts.evidence import EvidenceBundle
from groundtruth.contracts.identifiers import DatasetRef
from groundtruth.contracts.result import AnalysisError, AnalysisResult, ErrorCode, RunMetrics
from groundtruth.platform.compare.comparison import Comparison, NotComparable
from groundtruth.platform.compare.diff import BundleDiff
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


class VerificationRequest(BaseModel):
    """Options for a verification run."""

    synthetic: bool = Field(
        default=True,
        description=(
            "Must be true until real Earth-observation providers are implemented. A request "
            "with synthetic=false is rejected rather than silently simulated."
        ),
    )
    true_effect: float = Field(
        default=0.06, description="Effect injected into the simulated treated unit."
    )
    min_donors: int = Field(default=10, ge=2)
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
    data_mode: str = Field(description="'simulated' or 'observed'.")
    verdict_label: str
    verdict_rationale: str
    caveats: list[str]
    warnings: list[str]
    bundle: EvidenceBundle
    report_markdown: str | None = None
    report_generator: str | None = None


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

    @classmethod
    def build(
        cls, summary: RunSummary, result: AnalysisResult | None, *, include_bundle: bool
    ) -> RunDetail:
        item = RunItem.from_summary(summary)
        bundle = result.bundle if result else None
        verdict = bundle.verdict if bundle else None
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
