"""The analysis request: the engine's only input.

``AnalysisRequest`` is a complete, self-contained, serialisable description of
one analysis. The engine reads nothing else — no YAML, no database, no
environment variables, no filesystem. Everything it needs to run, and to be
re-run identically later, is in this object.

That property is what makes the engine a reproducible computational module
rather than a piece of the application, and it is what lets the platform queue,
cache, retry and replay analyses without knowing any engine internals.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from groundtruth.contracts.identifiers import DatasetRef, ModelRef, spec_hash
from groundtruth.contracts.types import Indicator
from groundtruth.contracts.version import CONTRACT_VERSION


class AnalysisWindow(BaseModel):
    """Pre- and post-treatment period ranges."""

    model_config = ConfigDict(frozen=True)

    pre_start: int
    pre_end: int
    post_start: int
    post_end: int

    @model_validator(mode="after")
    def _ordered(self) -> AnalysisWindow:
        if not self.pre_start < self.pre_end < self.post_start <= self.post_end:
            raise ValueError(
                f"invalid analysis window: pre {self.pre_start}-{self.pre_end}, "
                f"post {self.post_start}-{self.post_end}"
            )
        return self

    @property
    def n_pre_periods(self) -> int:
        """Number of pre-treatment periods."""
        return self.pre_end - self.pre_start + 1

    @property
    def n_post_periods(self) -> int:
        """Number of post-treatment periods."""
        return self.post_end - self.post_start + 1

    @property
    def periods(self) -> tuple[int, ...]:
        """Every period in the window."""
        return tuple(range(self.pre_start, self.post_end + 1))


class UnitRef(BaseModel):
    """A spatial unit the engine can observe: the project, or a donor candidate.

    Geometry is a GeoJSON-like mapping so the contract does not require GEOS or
    GDAL to be installed anywhere it is imported.
    """

    model_config = ConfigDict(frozen=True)

    unit_id: str
    geometry: dict[str, Any] | None = None
    centroid_lat: float | None = Field(default=None, ge=-90.0, le=90.0)
    centroid_lon: float | None = Field(default=None, ge=-180.0, le=180.0)
    area_ha: float | None = Field(default=None, gt=0.0)
    attributes: dict[str, float] = Field(default_factory=dict)

    @property
    def is_geometric(self) -> bool:
        """True if a real geometry, not just a centroid, is attached."""
        return self.geometry is not None


class DonorSpec(BaseModel):
    """How the donor pool should be built."""

    model_config = ConfigDict(frozen=True)

    candidates: tuple[UnitRef, ...] = Field(
        default=(),
        description=(
            "Candidate control units, resolved by the platform. When empty, the engine "
            "asks the DonorCandidateAccess port for them."
        ),
    )
    search_region: str = Field(default="", description="Human-readable description, for reports.")
    pool_size: int = Field(default=60, ge=2)
    max_donors: int = Field(default=50, ge=2)
    min_donors: int = Field(default=10, ge=2)
    covariates: tuple[str, ...] = Field(
        default=(
            "rainfall_mm",
            "elevation_m",
            "slope_deg",
            "road_distance_km",
            "population_density",
        )
    )
    covariate_weights: dict[str, float] = Field(default_factory=dict)
    caliper_sd: float | None = Field(default=3.0, gt=0.0)
    excluded_unit_ids: tuple[str, ...] = Field(
        default=(), description="Leakage-belt or otherwise contaminated units."
    )
    leakage_belt_km: float = Field(default=10.0, ge=0.0)
    min_pre_observations: int = Field(default=4, ge=1)

    @model_validator(mode="after")
    def _consistent(self) -> DonorSpec:
        if self.min_donors > self.max_donors:
            raise ValueError("min_donors cannot exceed max_donors")
        if not self.covariates:
            raise ValueError("at least one matching covariate is required")
        return self


class EstimationSpec(BaseModel):
    """Which estimators to run and how."""

    model_config = ConfigDict(frozen=True)

    primary: ModelRef = Field(default_factory=lambda: ModelRef(model_id="synthetic-control"))
    cross_checks: tuple[ModelRef, ...] = Field(
        default_factory=lambda: (ModelRef(model_id="difference-in-differences"),)
    )
    ridge: float = Field(default=0.0, ge=0.0)
    min_pre_periods: int = Field(default=5, ge=2)
    max_pre_rmse_ratio: float = Field(default=0.30, gt=0.0)


class RobustnessSpec(BaseModel):
    """Which robustness and uncertainty checks to run."""

    model_config = ConfigDict(frozen=True)

    in_space_placebo: bool = True
    in_time_placebo: bool = False
    leave_one_out: bool = True
    specification_curve: bool = False
    confidence_level: float = Field(default=0.95, gt=0.0, lt=1.0)
    max_placebo_pre_rmspe_multiple: float | None = Field(default=5.0, gt=0.0)


class ClaimUnderTest(BaseModel):
    """The developer's claim.

    Carried so it can be reported alongside the independent estimate. **It is
    never an input to the counterfactual.** The engine reads it only to record
    it as evidence marked ``developer_reported``.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    country: str = "unknown"
    standard: str = "Other"
    registry_id: str | None = None
    project_area_ha: float | None = Field(default=None, gt=0.0)
    claimed_credits_tco2e: float | None = None
    crediting_period_start: str | None = None
    crediting_period_end: str | None = None
    source_uri: str | None = None


class AnalysisRequest(BaseModel):
    """Everything the engine needs to run one analysis, and nothing else.

    Constructed by the platform from a stored case definition plus resolved
    dataset references. Fully serialisable: an identical request replayed later
    against the same engine version and datasets must produce an identical
    result.
    """

    model_config = ConfigDict(frozen=True)

    contract_version: str = Field(default=CONTRACT_VERSION)
    case_id: str = Field(description="Stable slug identifying the project under test.")
    project: UnitRef
    claim: ClaimUnderTest
    indicator: Indicator
    window: AnalysisWindow
    donors: DonorSpec = Field(default_factory=DonorSpec)
    estimation: EstimationSpec = Field(default_factory=EstimationSpec)
    robustness: RobustnessSpec = Field(default_factory=RobustnessSpec)

    datasets: tuple[DatasetRef, ...] = Field(
        default=(),
        description=(
            "Pinned dataset references resolved by the platform. The engine does not "
            "choose dataset versions."
        ),
    )
    seed: int = Field(default=20260101, description="Seed for every stochastic step.")
    data_mode: Literal["observed", "simulated"] = Field(
        default="simulated",
        description=(
            "Declared by the platform. 'simulated' propagates into the evidence bundle "
            "warnings and the verdict caveats, so a fixture run can never be published "
            "as a finding about a real project."
        ),
    )
    requested_by: str | None = None
    notes: str = ""

    @model_validator(mode="after")
    def _consistent(self) -> AnalysisRequest:
        if self.window.n_pre_periods < self.estimation.min_pre_periods:
            raise ValueError(
                f"window has {self.window.n_pre_periods} pre-treatment periods but the "
                f"estimation spec requires at least {self.estimation.min_pre_periods}"
            )
        if self.data_mode == "observed" and any(d.is_synthetic for d in self.datasets):
            raise ValueError(
                "data_mode='observed' but a synthetic dataset is referenced; a simulated "
                "run must never be labelled as observed"
            )
        return self

    @property
    def spec_hash(self) -> str:
        """Deterministic hash of the specification, excluding non-analytical fields.

        Two requests with the same hash must produce the same result under the
        same engine version. Used as the platform's cache key and as the
        reproducibility check in validation.
        """
        payload = self.model_dump(mode="json", exclude={"requested_by", "notes"})
        for dataset in payload.get("datasets", []):
            dataset.pop("retrieved_at", None)
        return spec_hash(payload)

    @property
    def is_simulated(self) -> bool:
        """True if this run uses simulated data."""
        return self.data_mode == "simulated" or any(d.is_synthetic for d in self.datasets)
