"""The analysis result: the engine's only output.

The engine returns an ``AnalysisResult`` for every domain outcome, including
failure. It does not raise for a project that cannot be analysed, because a
domain failure is information the platform must persist and show, not an
exception to catch at a job boundary and stringify.

Programming errors still raise. The distinction is deliberate: "this project
has no adequate donor pool" is a result; "this list index is out of range" is a
bug.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from groundtruth.contracts.evidence import EvidenceBundle
from groundtruth.contracts.identifiers import DatasetRef, EngineRef
from groundtruth.contracts.version import CONTRACT_VERSION


class EngineStatus(StrEnum):
    """Outcome of one engine invocation.

    Distinct from :class:`AnalysisStatus`, which tracks the platform's job
    lifecycle. A job can succeed (the engine ran to completion) while its
    engine status is ``refused`` (the data could not support an estimate).
    """

    COMPLETED = "completed"
    """The engine produced an evidence bundle with a verdict."""

    REFUSED = "refused"
    """The engine declined to estimate. A legitimate scientific outcome.

    Raised by an inadequate donor pool, a pre-period too short or too sparse, or
    an indicator that cannot support the requested comparison. Refusing is
    preferable to a fragile number and must be shown to the user as such, not
    as an error.
    """

    ERROR = "error"
    """The engine could not run. A malformed request or an internal failure."""


class AnalysisStatus(StrEnum):
    """Platform-side job lifecycle state.

    Owned by the platform; defined here so both sides agree on the vocabulary
    the API and the UI use.
    """

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    """The engine ran to completion. Check ``EngineStatus`` for what it found."""
    FAILED = "failed"
    """The job itself failed: timeout, crash, unavailable upstream data."""
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        """True if no further transition is expected."""
        return self in (AnalysisStatus.SUCCEEDED, AnalysisStatus.FAILED, AnalysisStatus.CANCELLED)


class ErrorCode(StrEnum):
    """Machine-readable failure reasons.

    The API maps these to HTTP status codes and the UI maps them to copy, so
    neither has to parse an error message. Adding a member is a minor contract
    change; changing what one means is a major one.
    """

    INVALID_REQUEST = "invalid_request"
    """The request failed validation. 422."""

    CONTRACT_VERSION_MISMATCH = "contract_version_mismatch"
    """The request targets a contract version this engine cannot serve. 409."""

    DATA_UNAVAILABLE = "data_unavailable"
    """A required dataset could not be retrieved. 503."""

    INSUFFICIENT_DATA = "insufficient_data"
    """Data exists but is too sparse to support an estimate. Refusal, not error."""

    DONOR_POOL_INADEQUATE = "donor_pool_inadequate"
    """No admissible donor pool could be constructed. Refusal, not error."""

    ESTIMATION_FAILED = "estimation_failed"
    """An estimator was mis-specified or failed to fit. 500."""

    NOT_IMPLEMENTED = "not_implemented"
    """A requested capability exists as an interface but not as an implementation. 501."""

    INTERNAL_ERROR = "internal_error"
    """An unexpected failure. 500."""

    @property
    def is_refusal(self) -> bool:
        """True if this code represents a scientific refusal, not a malfunction.

        A refusal is shown to the user as a legitimate outcome with an
        explanation. A malfunction is shown as a problem to be fixed.
        """
        return self in (ErrorCode.INSUFFICIENT_DATA, ErrorCode.DONOR_POOL_INADEQUATE)


class AnalysisError(BaseModel):
    """A structured failure the platform can persist, render and act on."""

    model_config = ConfigDict(frozen=True)

    code: ErrorCode
    message: str = Field(description="Plain-language explanation, safe to show a user.")
    stage: str = Field(default="unknown", description="Pipeline stage that failed.")
    detail: dict[str, Any] = Field(
        default_factory=dict, description="Structured context, e.g. donors found vs required."
    )
    remediation: str | None = Field(
        default=None, description="What the user or operator could do about it."
    )

    @property
    def is_refusal(self) -> bool:
        """True if this is a scientific refusal rather than a malfunction."""
        return self.code.is_refusal


class RunMetrics(BaseModel):
    """Timings and counters, for monitoring and capacity planning."""

    model_config = ConfigDict(frozen=True)

    duration_ms: float = Field(default=0.0, ge=0.0)
    stage_durations_ms: dict[str, float] = Field(default_factory=dict)
    n_units_observed: int = Field(default=0, ge=0)
    n_donors_admitted: int = Field(default=0, ge=0)
    n_estimator_fits: int = Field(default=0, ge=0)


class AnalysisResult(BaseModel):
    """The engine's complete output for one request.

    Serialisable and self-describing. The platform persists this object; the API
    serves projections of it; the reporting layer narrates its bundle. None of
    them need to import anything from ``groundtruth.engine``.
    """

    model_config = ConfigDict(frozen=True)

    contract_version: str = Field(default=CONTRACT_VERSION)
    run_id: str
    case_id: str
    spec_hash: str = Field(description="Hash of the request specification that produced this.")
    status: EngineStatus
    engine: EngineRef
    datasets: tuple[DatasetRef, ...] = ()
    seed: int = 20260101
    data_mode: str = Field(default="simulated", description="'observed' or 'simulated'.")
    started_at: str | None = None
    finished_at: str | None = None

    bundle: EvidenceBundle | None = Field(
        default=None, description="Present when status is COMPLETED."
    )
    error: AnalysisError | None = Field(
        default=None, description="Present when status is REFUSED or ERROR."
    )
    metrics: RunMetrics = Field(default_factory=RunMetrics)

    @model_validator(mode="after")
    def _consistent(self) -> AnalysisResult:
        if self.status is EngineStatus.COMPLETED and self.bundle is None:
            raise ValueError("a completed result must carry an evidence bundle")
        if self.status is not EngineStatus.COMPLETED and self.error is None:
            raise ValueError(f"a {self.status.value} result must carry an error")
        return self

    @property
    def is_simulated(self) -> bool:
        """True if this result came from simulated data.

        The UI uses this to decide whether to show the persistent
        simulated-data banner. It must never be inferred from anything softer.
        """
        return self.data_mode == "simulated" or any(d.is_synthetic for d in self.datasets)

    @property
    def verdict_label(self) -> str:
        """The verdict label, or a stand-in when no bundle was produced."""
        if self.bundle is not None and self.bundle.verdict is not None:
            return self.bundle.verdict.label.value
        return "not_assessed"
