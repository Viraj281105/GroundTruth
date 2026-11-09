"""Value types of the assessment engine.

Everything here is a frozen dataclass of plain Python values, so an assessment
can be compared, hashed by content and serialized by the platform without the
engine knowing how. Vocabularies are the ones fixed by spec section 6A.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

# -- vocabularies -----------------------------------------------------------------------

STATUSES: frozenset[str] = frozenset(
    {
        "Improving",
        "Deteriorating",
        "Stable",
        "Mixed spatial performance",
        "Elevated ecological risk",
        "No clear change",
        "Insufficient evidence",
    }
)
ATTRIBUTION_VERDICTS: frozenset[str] = frozenset({"Supported", "Not supported", "Inconclusive"})
# Dimension 7 (evidence quality) is a rating, not a change status; its rating sits in `status`.
EVIDENCE_RATINGS: frozenset[str] = frozenset({"High", "Moderate", "Low"})
LIMITATIONS: frozenset[str] = frozenset(
    {
        "missing_data",
        "weak_statistical_power",
        "poor_reference_comparability",
        "climate_confounding",
        "failed_model_assumptions",
        "none",
    }
)
CONFIDENCES: frozenset[str] = EVIDENCE_RATINGS
PERSONAS: tuple[str, ...] = ("ngo", "funder", "auditor", "government", "reference")

Limitation = Literal[
    "missing_data",
    "weak_statistical_power",
    "poor_reference_comparability",
    "climate_confounding",
    "failed_model_assumptions",
    "none",
]
DataMode = Literal["observed", "simulated"]

# -- inputs -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SeriesPoint:
    """One annual index value for the project AOI (or a zone or reference unit)."""

    year: int
    value: float
    n_valid_pixels: int
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SpreadPoint:
    """Within-AOI spread of an index for one year, from stored zonal statistics."""

    year: int
    p10: float
    p90: float
    std: float
    n_valid_pixels: int
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ClimateYear:
    """Annual climate context. Any field may be absent; absent is never filled in."""

    year: int
    rainfall_mm: float | None = None
    spi12: float | None = None
    temperature_c: float | None = None
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReadinessSummary:
    """What the engine needs from the platform's computed project readiness.

    The platform adapter maps ``ProjectReadiness`` (Task 8) onto this type; the engine
    never imports the platform. The ``causal_*`` fields summarize a real-data causal
    run, if one completed. The engine cannot run one itself.
    """

    attribution_ready: bool
    pre_treatment_observed: bool
    donor_panel_available: bool
    boundary_verified: bool
    climate_missing_months: tuple[str, ...]
    provenance_ok: bool = True
    causal_run_completed: bool = False
    causal_verdict: str | None = None  # Supported | Not supported | Inconclusive
    causal_limitation: str | None = None
    causal_methodology: str | None = None
    causal_evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class AssessmentInputs:
    """Real artifacts gathered by the platform, ready for the pure engine.

    ``series`` is indicator -> annual AOI points; ``reference_series`` is
    indicator -> donor id -> points; ``zone_series`` is indicator -> zone id -> points
    (only when per-zone composites are persisted); ``zonal_spread`` is indicator ->
    per-year within-AOI spread.
    """

    series: Mapping[str, list[SeriesPoint]]
    zonal_spread: Mapping[str, list[SpreadPoint]] | None = None
    climate: list[ClimateYear] | None = None
    reference_series: Mapping[str, Mapping[str, list[SeriesPoint]]] | None = None
    readiness: ReadinessSummary
    coverage_pct: Mapping[int, float] = field(default_factory=dict)
    sensors: Mapping[int, list[str]] = field(default_factory=dict)
    field_evidence: bool = False
    treatment_start_year: int
    data_mode: DataMode = "observed"
    zone_series: Mapping[str, Mapping[str, list[SeriesPoint]]] | None = None
    claim_present: bool = False


# -- outputs ----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DimensionResult:
    """One of the eight dimensions, independent of attribution.

    ``status`` is a change status for dimensions 1-6, a High/Moderate/Low rating for
    dimension 7 and an attribution verdict for dimension 8. ``facts`` carries the
    machine-readable values the recommendation rules read.
    """

    id: str
    title: str
    status: str
    finding: str
    known: tuple[str, ...]
    suggested: tuple[str, ...]
    cannot_establish: tuple[str, ...]
    limitation: Limitation
    evidence_needed: str
    confidence: str
    evidence_refs: tuple[str, ...]
    facts: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in STATUSES | EVIDENCE_RATINGS | ATTRIBUTION_VERDICTS:
            raise ValueError(f"unknown dimension status {self.status!r}")
        if self.limitation not in LIMITATIONS:
            raise ValueError(f"unknown limitation {self.limitation!r}")
        if self.confidence not in CONFIDENCES:
            raise ValueError(f"unknown confidence {self.confidence!r}")


@dataclass(frozen=True, slots=True)
class AttributionResult:
    verdict: str
    methodology: str
    limitation: Limitation
    finding: str
    evidence_needed: str
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.verdict not in ATTRIBUTION_VERDICTS:
            raise ValueError(f"unknown attribution verdict {self.verdict!r}")
        if self.limitation not in LIMITATIONS:
            raise ValueError(f"unknown limitation {self.limitation!r}")


@dataclass(frozen=True, slots=True)
class Conclusion:
    """One layered conclusion: a deterministic sentence, or not-estimable plus its reason."""

    summary: str
    dimension_ids: tuple[str, ...]
    estimable: bool = True
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class Recommendation:
    id: str
    text: str
    rationale: str
    priority: int  # 1 is the most urgent
    personas: tuple[str, ...]
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Assessment:
    level: int
    level_name: str
    dimensions: tuple[DimensionResult, ...]
    observed_outcome: Conclusion
    ecological_assessment: Conclusion
    climate_adjusted_interpretation: Conclusion
    comparative_assessment: Conclusion
    attribution: AttributionResult
    evidence_confidence: str
    recommendations: tuple[Recommendation, ...]
    data_mode: DataMode = "observed"
    simulated_banner: str | None = None
