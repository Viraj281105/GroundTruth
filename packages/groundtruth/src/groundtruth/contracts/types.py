"""Shared domain types for the GroundTruth pipeline."""

from __future__ import annotations

from datetime import date
from enum import StrEnum

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Indicator(StrEnum):
    """Observable indicators the pipeline can track through time.

    These are *observations*, not carbon. See :mod:`groundtruth.contracts.units`.
    """

    NDVI = "ndvi"
    EVI = "evi"
    NBR = "nbr"
    TREE_COVER_FRACTION = "tree_cover_fraction"
    FOREST_AREA_HA = "forest_area_ha"
    CUMULATIVE_LOSS_HA = "cumulative_loss_ha"


INDICATOR_UNITS: dict[Indicator, str] = {
    Indicator.NDVI: "ndvi",
    Indicator.EVI: "evi",
    Indicator.NBR: "nbr",
    Indicator.TREE_COVER_FRACTION: "fraction",
    Indicator.FOREST_AREA_HA: "ha",
    Indicator.CUMULATIVE_LOSS_HA: "ha",
}

STANDARD_CAVEATS: tuple[str, ...] = (
    "A divergence between an independent estimate and a developer claim is not evidence of "
    "fraud; it indicates that the claim warrants accredited review.",
    "Spectral indices track vegetation condition, not carbon stocks.",
    "Estimates are conditional on the donor pool and the pre-treatment fit reported alongside "
    "them.",
)


class MethodologyStandard(StrEnum):
    """Crediting standard a project is registered under."""

    VCS = "VCS"
    GOLD_STANDARD = "GoldStandard"
    PLAN_VIVO = "PlanVivo"
    OTHER = "Other"


class ProjectClaim(BaseModel):
    """A claim made by a project developer that GroundTruth will screen.

    The claim is treated purely as an *assertion under test*. Nothing in it is
    used to construct the counterfactual.
    """

    model_config = ConfigDict(frozen=True)

    case_id: str = Field(description="Stable slug, e.g. 'kariba-redd'.")
    name: str
    country: str
    standard: MethodologyStandard = MethodologyStandard.OTHER
    registry_id: str | None = Field(default=None, description="e.g. 'VCS 902'.")
    project_area_ha: float | None = Field(default=None, gt=0)
    crediting_period_start: date | None = None
    crediting_period_end: date | None = None
    claimed_credits_tco2e: float | None = Field(
        default=None, description="Credits claimed/issued, as reported by the registry."
    )
    claim_source_uri: str | None = None
    boundary_path: str | None = Field(
        default=None, description="Relative path to the project boundary geometry."
    )

    @property
    def treatment_year(self) -> int | None:
        """Year the intervention is assumed to begin."""
        return self.crediting_period_start.year if self.crediting_period_start else None


class TimeSeries(BaseModel):
    """A regularly indexed observation series for one unit (project or donor)."""

    model_config = ConfigDict(frozen=True)

    unit_id: str
    indicator: Indicator
    periods: tuple[int, ...] = Field(description="Ordered period labels, typically years.")
    values: tuple[float, ...]
    unit: str = Field(default="", description="Measurement unit; defaults from the indicator.")
    n_valid_observations: tuple[int, ...] | None = Field(
        default=None, description="Clear-sky observation count backing each period."
    )

    @model_validator(mode="after")
    def _check(self) -> TimeSeries:
        if len(self.periods) != len(self.values):
            raise ValueError("periods and values must have the same length")
        if len(self.periods) < 2:
            raise ValueError("a time series needs at least two periods")
        if list(self.periods) != sorted(self.periods):
            raise ValueError("periods must be sorted ascending")
        if len(set(self.periods)) != len(self.periods):
            raise ValueError("periods must be unique")
        if not self.unit:
            object.__setattr__(self, "unit", INDICATOR_UNITS[self.indicator])
        return self

    def as_array(self) -> np.ndarray:
        """Values as a float array."""
        return np.asarray(self.values, dtype=float)

    def window(self, start: int, end: int) -> np.ndarray:
        """Values for periods in the inclusive range ``[start, end]``."""
        idx = [i for i, p in enumerate(self.periods) if start <= p <= end]
        if not idx:
            raise ValueError(f"no periods in [{start}, {end}] for unit {self.unit_id}")
        return self.as_array()[idx]


class DonorMatch(BaseModel):
    """One candidate control unit with its covariate distance to the project."""

    model_config = ConfigDict(frozen=True)

    unit_id: str
    distance: float = Field(ge=0.0, description="Standardised covariate distance (lower=closer).")
    covariates: dict[str, float] = Field(default_factory=dict)
    admitted: bool = Field(default=True, description="False if excluded by an eligibility rule.")
    exclusion_reason: str | None = None


class Confidence(BaseModel):
    """An interval estimate with an explicit interpretation.

    ``kind`` records whether the interval is a classical confidence interval, a
    permutation-based range, or a sensitivity envelope. Reporting these as if
    they were interchangeable would be misleading.
    """

    model_config = ConfigDict(frozen=True)

    lower: float
    upper: float
    level: float = Field(default=0.95, gt=0.0, lt=1.0)
    kind: str = Field(
        default="permutation",
        description="permutation | bootstrap | analytic | sensitivity-envelope",
    )

    @model_validator(mode="after")
    def _ordered(self) -> Confidence:
        if self.lower > self.upper:
            raise ValueError("lower bound must not exceed upper bound")
        return self

    def contains(self, value: float) -> bool:
        """True if ``value`` lies inside the interval."""
        return self.lower <= value <= self.upper


class CausalEffect(BaseModel):
    """An estimated treatment effect on an *observed indicator*.

    This object never carries carbon units unless an explicit biomass conversion
    step has been applied and recorded in its provenance.
    """

    model_config = ConfigDict(frozen=True)

    indicator: Indicator
    unit: str
    estimator: str = Field(description="e.g. 'synthetic-control', 'difference-in-differences'.")
    point_estimate: float
    confidence: Confidence | None = None
    placebo_p_value: float | None = Field(default=None, ge=0.0, le=1.0)
    pre_period_fit_rmse: float | None = Field(default=None, ge=0.0)
    post_pre_rmspe_ratio: float | None = Field(default=None, ge=0.0)
    n_donors_used: int | None = Field(default=None, ge=0)
    treatment_period: int | None = None
    notes: str | None = None

    @property
    def is_statistically_distinguishable(self) -> bool:
        """True only if a placebo p-value is available and below 0.10.

        Absence of evidence is reported as ``False``, never as a positive
        finding in the opposite direction.
        """
        return self.placebo_p_value is not None and self.placebo_p_value < 0.10


class VerdictLabel(StrEnum):
    """Screening outcomes. None of these is a finding of fraud."""

    CONSISTENT_WITH_CLAIM = "consistent_with_claim"
    """Observed incremental effect is compatible with the developer's claim."""

    DIVERGENT_FROM_CLAIM = "divergent_from_claim"
    """Independent estimate diverges materially from the claim; warrants review."""

    INCONCLUSIVE = "inconclusive"
    """Data or donor pool cannot support a defensible estimate."""

    NOT_ASSESSED = "not_assessed"
    """Pipeline did not run to completion for this case."""


class VerificationVerdict(BaseModel):
    """The screening conclusion, phrased so it cannot be read as an accusation."""

    model_config = ConfigDict(frozen=True)

    label: VerdictLabel
    rationale: str
    divergence_ratio: float | None = Field(
        default=None,
        description="Independent estimate / claimed effect, where both are commensurable.",
    )
    caveats: tuple[str, ...] = Field(default=STANDARD_CAVEATS)
    supporting_evidence_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _always_caveated(self) -> VerificationVerdict:
        missing = [c for c in STANDARD_CAVEATS if c not in self.caveats]
        if missing:
            object.__setattr__(self, "caveats", tuple(self.caveats) + tuple(missing))
        return self
