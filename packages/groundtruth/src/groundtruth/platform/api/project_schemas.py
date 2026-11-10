"""Response models of the project data routes (``/projects/{id}/readiness`` and friends).

Every response carries ``data_mode`` and ``access_level``. A field that only some levels may see
is declared with ``min_level(...)``: it is absent (not ``null``) below that level, and the
declaring models keep it optional so the generated client types it as such. Redaction removes
fields and never changes values (``platform/projects/redaction.py``).

``status`` is ``available`` or ``unavailable`` wherever a series is served; ``unavailable``
always comes with the loader's specific ``reason`` and never with fabricated values.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from groundtruth.contracts.evidence import EvidenceBundle
from groundtruth.platform.api.schemas import DataModeName, ProjectLevelName
from groundtruth.platform.projects.redaction import min_level

Availability = Literal["available", "unavailable"]
Indicator = Literal["ndvi", "evi", "ndmi", "nbr"]
EvidenceStateName = Literal["DERIVED", "MODEL_ESTIMATED", "UNAVAILABLE"]


class ProjectDataResponse(BaseModel):
    """Fields every project data response carries."""

    data_mode: DataModeName = Field(description="'simulated' data is never real data (R7).")
    access_level: ProjectLevelName = Field(description="The caller's level on this project.")


# --- readiness -------------------------------------------------------------------------------


class ReadinessCriterion(BaseModel):
    """One condition for attempting causal attribution, and whether it holds."""

    model_config = ConfigDict(use_attribute_docstrings=True)
    id: str
    """Stable criterion id."""
    name: str
    """Criterion name for display."""
    status: Literal["met", "not_met", "unavailable"]
    """`met`, `not_met`, or `unavailable` when the evidence to judge it is missing."""
    observed_value: Any = None
    """What the project's evidence shows for this criterion."""
    required: Any = None
    """What the criterion requires."""
    evidence_needed: str
    """What would let this criterion be met or judged."""


class ReadinessBody(BaseModel):
    """Whether causal attribution can be attempted, criterion by criterion."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    attribution_ready: bool
    """True when every criterion is met and attribution can be attempted."""
    criteria: list[ReadinessCriterion]
    """Each criterion and its status."""


class ReadinessView(ProjectDataResponse, ReadinessBody):
    """``ReadinessBody`` as its own response (with ``data_mode`` and ``access_level``)."""


# --- observations ----------------------------------------------------------------------------


class ObservationPoint(BaseModel):
    """One calendar year of one indicator for the project AOI."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    year: int
    """Calendar year."""
    value: float | None = Field(description="Null when nothing was observed that year.")
    evidence_state: EvidenceStateName
    """How the value was obtained: `DERIVED`, `MODEL_ESTIMATED` or `UNAVAILABLE`."""
    sensor: str
    """Satellite sensor the scenes came from."""
    clear_pixel_fraction: float = Field(description="Share of scene pixels that were clear.")
    n_scenes: int
    """How many scenes contributed to the year."""
    aoi_coverage_pct: float | None = Field(
        default=None,
        description="Share of the project AOI actually observed, computed from valid pixels "
        "and the project boundary; null when it cannot be computed.",
    )
    scene_ids: list[str] | None = Field(default=None, json_schema_extra=min_level("contribute"))
    """Identifiers of those scenes. Absent below the `contribute` level."""
    scenes_sha256: str | None = Field(default=None, json_schema_extra=min_level("contribute"))
    """SHA-256 over the scene list. Absent below the `contribute` level."""


class ObservationsView(ProjectDataResponse):
    """The project's annual observations of one indicator."""

    model_config = ConfigDict(use_attribute_docstrings=True)
    indicator: Indicator
    """The vegetation index observed."""
    status: Availability
    """`available`, or `unavailable` with `reason` and no values."""
    reason: str | None = None
    """Why the series is unavailable."""
    unit_id: str | None = None
    """The observation unit the series belongs to."""
    source: str | None = None
    """Where the observations come from."""
    points: list[ObservationPoint] = Field(default_factory=list)
    """One entry per year."""


# --- climate ---------------------------------------------------------------------------------


class ClimateYearView(BaseModel):
    """One calendar year of the project's climate record."""

    model_config = ConfigDict(use_attribute_docstrings=True)
    year: int
    """Calendar year."""
    valid_months: int
    """Months with valid data, out of 12."""
    is_complete_year: bool
    """True when all 12 months are valid."""
    annual_rainfall_mm: float | None = None
    """Total rainfall, in millimetres."""
    rainfall_anomaly_mm: float | None = None
    """Rainfall minus the long-term mean, in millimetres."""
    rainfall_anomaly_z: float | None = None
    """The anomaly in standard deviations."""
    spi_12: float | None = None
    """12-month Standardized Precipitation Index."""
    drought_classification: str
    """Drought class derived from the SPI."""
    mean_temp_c: float | None = None
    """Mean temperature, in degrees Celsius."""


class ClimateSourceView(BaseModel):
    """A climate dataset the record draws on."""

    model_config = ConfigDict(use_attribute_docstrings=True)
    name: str
    """Dataset name."""
    dataset_id: str
    """Dataset identifier."""
    provider: str
    """Who publishes it."""
    citation: str
    """How to cite it."""
    temporal_coverage_start: str
    """First date it covers."""
    temporal_coverage_end: str
    """Last date it covers."""
    known_coverage_gaps: list[str] = Field(default_factory=list)
    """Known gaps in its coverage."""


class ClimateView(ProjectDataResponse):
    """The project's climate record, or why it is unavailable."""

    model_config = ConfigDict(use_attribute_docstrings=True)
    status: Availability
    """`available`, or `unavailable` with `reason` and no values."""
    reason: str | None = None
    """Why the record is unavailable."""
    case_id: str | None = None
    """The case the record belongs to."""
    sources: list[ClimateSourceView] = Field(default_factory=list)
    """Datasets the record draws on."""
    missing_months: list[str] = Field(default_factory=list)
    """Months with no valid data, as `YYYY-MM`."""
    years: list[ClimateYearView] = Field(default_factory=list)
    """One entry per year."""
    bundle_sha256: str | None = Field(default=None, json_schema_extra=min_level("contribute"))
    """SHA-256 of the stored climate bundle. Absent below the `contribute` level."""


# --- evidence inventory ----------------------------------------------------------------------


class InventoryItem(BaseModel):
    """One stored annual record; scene-level detail for EVIDENCE_FULL levels only."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    indicator: Indicator
    """The vegetation index."""
    year: int
    """Calendar year."""
    n_scenes: int
    """How many scenes contributed."""
    scene_ids: list[str] = Field(json_schema_extra=min_level("contribute"))
    """Identifiers of those scenes."""
    scenes_sha256: str = Field(json_schema_extra=min_level("contribute"))
    """SHA-256 over the scene list."""


class IndicatorInventory(BaseModel):
    """What is stored for one indicator."""

    model_config = ConfigDict(use_attribute_docstrings=True)
    indicator: Indicator
    """The vegetation index."""
    status: Availability
    """`available`, or `unavailable` with `reason`."""
    reason: str | None = None
    """Why nothing is available."""
    n_records: int = 0
    """How many annual records exist."""
    years: list[int] = Field(default_factory=list)
    """The years with a record."""
    states: dict[str, int] = Field(default_factory=dict)
    """Record counts by evidence state."""
    sensors: list[str] = Field(default_factory=list)
    """Sensors the records came from."""
    source: str | None = None
    """Where the records come from."""
    data_origin: str | None = None
    """Whether the records are real observations or simulated."""


class EvidenceInventoryView(ProjectDataResponse):
    """What evidence exists for the project. Everyone sees counts, kinds, states and sources;
    checksums, scene ids and the item list need ``EVIDENCE_FULL``."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    status: Availability
    """`available`, or `unavailable` with `reason`."""
    reason: str | None = None
    """Why nothing is available."""
    kinds: list[str] = Field(default_factory=list)
    """Kinds of evidence present."""
    indicators: list[IndicatorInventory] = Field(default_factory=list)
    """One entry per indicator."""
    states: dict[str, int] = Field(default_factory=dict)
    """Record counts by evidence state, across indicators."""
    climate_status: Availability
    """Whether a climate record is available."""
    climate_reason: str | None = None
    """Why the climate record is unavailable."""
    boundary_sha256: str | None = Field(default=None, json_schema_extra=min_level("contribute"))
    """SHA-256 of the stored boundary. Absent below the `contribute` level."""
    items: list[InventoryItem] | None = Field(
        default=None, json_schema_extra=min_level("contribute")
    )
    """Every stored annual record. Absent below the `contribute` level."""


# --- verification ----------------------------------------------------------------------------


class VerificationView(ProjectDataResponse):
    """The latest completed run for the project, or ``not_estimable`` when there is none."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    status: Literal["completed", "not_estimable"]
    """`completed`, or `not_estimable` when no completed run exists."""
    readiness: ReadinessBody
    """Whether attribution can be attempted, criterion by criterion."""
    warnings: list[str] = Field(
        default_factory=list, description="Includes the SIMULATED DATA notice (R7) when it applies."
    )
    is_simulated: bool
    """True when the run used simulated data."""
    run_id: str | None = None
    """The latest completed run."""
    case_id: str | None = None
    """The case that run analysed."""
    verdict_label: str | None = None
    """The run's screening verdict."""
    verdict_rationale: str | None = None
    """Why the engine reached it."""
    caveats: list[str] = Field(default_factory=list)
    """Statements that must accompany the verdict."""
    engine_version: str | None = None
    """Engine version of the run."""
    created_at: datetime | None = None
    """When the run was recorded."""
    spec_hash: str | None = Field(default=None, json_schema_extra=min_level("audit"))
    """Hash of the run's specification. Absent below the `audit` level."""
    bundle: EvidenceBundle | None = Field(default=None, json_schema_extra=min_level("audit"))
    """The run's evidence bundle. Absent below the `audit` level."""


# --- assessment ------------------------------------------------------------------------------

StatusKind = Literal["trend_status", "quality_rating", "attribution_verdict"]


class DimensionView(BaseModel):
    """One of the eight assessment dimensions."""

    model_config = ConfigDict(use_attribute_docstrings=True)
    id: str
    """Dimension id."""
    title: str
    """Dimension title."""
    status: str
    """A change status (Improving, Deteriorating, Stable, Mixed spatial performance, Elevated
    ecological risk, No clear change, Insufficient evidence) for dimensions 1-6; a High/Moderate/Low
    rating for dimension 7; an attribution verdict (Supported, Not supported, Inconclusive) for
    dimension 8."""
    status_kind: StatusKind = Field(
        description="What `status` means: a change status (dimensions 1-6), an evidence-quality "
        "rating (7) or an attribution verdict (8)."
    )
    finding: str
    """The finding, in one sentence."""
    known: list[str]
    """What the evidence establishes."""
    suggested: list[str]
    """What the evidence suggests but does not establish."""
    cannot_establish: list[str]
    """What the evidence cannot establish."""
    limitation: str
    """The main limitation: missing_data, weak_statistical_power, poor_reference_comparability,
    climate_confounding, failed_model_assumptions or none."""
    evidence_needed: str
    """What evidence would strengthen the finding."""
    confidence: str
    """High, Moderate or Low."""
    evidence_refs: list[str] = Field(
        description="References to observations, climate records and other dimensions."
    )
    diagnostic_refs: list[str] | None = Field(
        default=None,
        description="References into causal-run diagnostics.",
        json_schema_extra=min_level("audit"),
    )
    facts: dict[str, Any] = Field(default_factory=dict)
    """Machine-readable values behind the finding."""


class ConclusionView(BaseModel):
    """One layered conclusion, or why it cannot be drawn."""

    model_config = ConfigDict(use_attribute_docstrings=True)
    summary: str
    """The conclusion, in plain language."""
    dimension_ids: list[str]
    """Dimensions it rests on."""
    estimable: bool
    """False when the evidence cannot support this conclusion; see `reason`."""
    reason: str | None = None
    """Why it cannot be drawn."""


class AttributionView(BaseModel):
    """Whether the observed change can be attributed to the project."""

    model_config = ConfigDict(use_attribute_docstrings=True)
    verdict: str
    """Supported, Not supported or Inconclusive."""
    methodology: str
    """How attribution was assessed."""
    limitation: str
    """The main limitation on the verdict."""
    finding: str
    """The finding, in one sentence."""
    evidence_needed: str
    """What evidence would strengthen it."""
    evidence_refs: list[str]
    """Evidence ids it rests on."""
    diagnostic_refs: list[str] | None = Field(default=None, json_schema_extra=min_level("audit"))
    """Diagnostics behind it. Absent below the `audit` level."""


class RecommendationView(BaseModel):
    """A suggested next step."""

    model_config = ConfigDict(use_attribute_docstrings=True)
    id: str
    """Recommendation id."""
    text: str
    """What to do."""
    rationale: str
    """Why."""
    priority: int
    """1 is the most urgent."""
    personas: list[str]
    """Who it is for: ngo, funder, auditor, government or reference."""
    evidence_refs: list[str]
    """Evidence ids it rests on."""
    diagnostic_refs: list[str] | None = Field(default=None, json_schema_extra=min_level("audit"))
    """Diagnostics behind it. Absent below the `audit` level."""


class AssessmentView(ProjectDataResponse):
    """The project's layered assessment: what is known, at what level of evidence."""

    model_config = ConfigDict(use_attribute_docstrings=True)
    level: int
    """Assessment level reached, 0 to 5."""
    level_name: str
    """Not assessable, Basic monitoring, Contextual intelligence, Comparative intelligence,
    Attribution assessment or Verified impact; `(simulated)` is appended for simulated data."""
    evidence_confidence: str
    """Overall confidence in the evidence: High, Moderate or Low."""
    simulated_banner: str | None = None
    """The notice to show when the assessment rests on simulated data."""
    observed_outcome: ConclusionView
    """What was observed."""
    ecological_assessment: ConclusionView
    """What it means ecologically."""
    climate_adjusted_interpretation: ConclusionView
    """The observation read against the climate record."""
    comparative_assessment: ConclusionView
    """The project against comparable areas."""
    attribution: AttributionView
    """Whether the change can be attributed to the project."""
    dimensions: list[DimensionView]
    """The eight dimensions."""
    recommendations: list[RecommendationView]
    """Suggested next steps, most urgent first."""
