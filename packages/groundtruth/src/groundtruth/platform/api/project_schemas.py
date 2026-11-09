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

from pydantic import BaseModel, Field

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
    id: str
    name: str
    status: Literal["met", "not_met", "unavailable"]
    observed_value: Any = None
    required: Any = None
    evidence_needed: str


class ReadinessBody(BaseModel):
    """Whether causal attribution can be attempted, criterion by criterion."""

    attribution_ready: bool
    criteria: list[ReadinessCriterion]


class ReadinessView(ProjectDataResponse, ReadinessBody):
    """``ReadinessBody`` as its own response (with ``data_mode`` and ``access_level``)."""


# --- observations ----------------------------------------------------------------------------


class ObservationPoint(BaseModel):
    """One calendar year of one indicator for the project AOI."""

    year: int
    value: float | None = Field(description="Null when nothing was observed that year.")
    evidence_state: EvidenceStateName
    sensor: str
    clear_pixel_fraction: float = Field(description="Share of scene pixels that were clear.")
    n_scenes: int
    aoi_coverage_pct: float | None = Field(
        default=None,
        description="Share of the project AOI actually observed, computed from valid pixels "
        "and the project boundary; null when it cannot be computed.",
    )
    scene_ids: list[str] | None = Field(default=None, json_schema_extra=min_level("contribute"))
    scenes_sha256: str | None = Field(default=None, json_schema_extra=min_level("contribute"))


class ObservationsView(ProjectDataResponse):
    indicator: Indicator
    status: Availability
    reason: str | None = None
    unit_id: str | None = None
    source: str | None = None
    points: list[ObservationPoint] = Field(default_factory=list)


# --- climate ---------------------------------------------------------------------------------


class ClimateYearView(BaseModel):
    year: int
    valid_months: int
    is_complete_year: bool
    annual_rainfall_mm: float | None = None
    rainfall_anomaly_mm: float | None = None
    rainfall_anomaly_z: float | None = None
    spi_12: float | None = None
    drought_classification: str
    mean_temp_c: float | None = None


class ClimateSourceView(BaseModel):
    name: str
    dataset_id: str
    provider: str
    citation: str
    temporal_coverage_start: str
    temporal_coverage_end: str
    known_coverage_gaps: list[str] = Field(default_factory=list)


class ClimateView(ProjectDataResponse):
    status: Availability
    reason: str | None = None
    case_id: str | None = None
    sources: list[ClimateSourceView] = Field(default_factory=list)
    missing_months: list[str] = Field(default_factory=list)
    years: list[ClimateYearView] = Field(default_factory=list)
    bundle_sha256: str | None = Field(default=None, json_schema_extra=min_level("contribute"))


# --- evidence inventory ----------------------------------------------------------------------


class InventoryItem(BaseModel):
    """One stored annual record; scene-level detail for EVIDENCE_FULL levels only."""

    indicator: Indicator
    year: int
    n_scenes: int
    scene_ids: list[str] = Field(json_schema_extra=min_level("contribute"))
    scenes_sha256: str = Field(json_schema_extra=min_level("contribute"))


class IndicatorInventory(BaseModel):
    indicator: Indicator
    status: Availability
    reason: str | None = None
    n_records: int = 0
    years: list[int] = Field(default_factory=list)
    states: dict[str, int] = Field(default_factory=dict)
    sensors: list[str] = Field(default_factory=list)
    source: str | None = None
    data_origin: str | None = None


class DocumentSummary(BaseModel):
    """One uploaded project document. ``status`` says how far processing went, never more."""

    id: str
    filename: str
    content_type: str
    size_bytes: int
    sha256: str | None = Field(default=None, json_schema_extra=min_level("contribute"))
    uploaded_at: datetime
    status: Literal["uploaded", "text_extracted", "extraction_unsupported", "extraction_failed"]
    status_detail: str | None = None
    extracted_claims_count: int | None = None


class ObservationIngestionStatus(BaseModel):
    """Whether any path exists to ingest satellite observations for this project."""

    available: bool
    message: str


class EvidenceInventoryView(ProjectDataResponse):
    """What evidence exists for the project. Everyone sees counts, kinds, states and sources;
    checksums, scene ids and the item list need ``EVIDENCE_FULL``."""

    status: Availability
    reason: str | None = None
    kinds: list[str] = Field(default_factory=list)
    indicators: list[IndicatorInventory] = Field(default_factory=list)
    states: dict[str, int] = Field(default_factory=dict)
    climate_status: Availability
    climate_reason: str | None = None
    boundary_sha256: str | None = Field(default=None, json_schema_extra=min_level("contribute"))
    items: list[InventoryItem] | None = Field(
        default=None, json_schema_extra=min_level("contribute")
    )
    documents_count: int = 0
    documents_by_status: dict[str, int] = Field(default_factory=dict)
    documents: list[DocumentSummary] | None = Field(
        default=None, json_schema_extra=min_level("contribute")
    )
    missing_evidence: list[str] = Field(
        default_factory=list, description="What is still missing, in plain language."
    )
    next_steps: list[str] = Field(
        default_factory=list, description="What the user can do next; only real capabilities."
    )
    observation_ingestion: ObservationIngestionStatus | None = None


# --- verification ----------------------------------------------------------------------------


class VerificationView(ProjectDataResponse):
    """The latest completed run for the project, or ``not_estimable`` when there is none."""

    status: Literal["completed", "not_estimable"]
    readiness: ReadinessBody
    warnings: list[str] = Field(
        default_factory=list, description="Includes the SIMULATED DATA notice (R7) when it applies."
    )
    is_simulated: bool
    run_id: str | None = None
    case_id: str | None = None
    verdict_label: str | None = None
    verdict_rationale: str | None = None
    caveats: list[str] = Field(default_factory=list)
    engine_version: str | None = None
    created_at: datetime | None = None
    spec_hash: str | None = Field(default=None, json_schema_extra=min_level("audit"))
    bundle: EvidenceBundle | None = Field(default=None, json_schema_extra=min_level("audit"))


# --- assessment ------------------------------------------------------------------------------

StatusKind = Literal["trend_status", "quality_rating", "attribution_verdict"]


class DimensionView(BaseModel):
    id: str
    title: str
    status: str
    status_kind: StatusKind = Field(
        description="What `status` means: a change status (dimensions 1-6), an evidence-quality "
        "rating (7) or an attribution verdict (8)."
    )
    finding: str
    known: list[str]
    suggested: list[str]
    cannot_establish: list[str]
    limitation: str
    evidence_needed: str
    confidence: str
    evidence_refs: list[str] = Field(
        description="References to observations, climate records and other dimensions."
    )
    diagnostic_refs: list[str] | None = Field(
        default=None,
        description="References into causal-run diagnostics.",
        json_schema_extra=min_level("audit"),
    )
    facts: dict[str, Any] = Field(default_factory=dict)


class ConclusionView(BaseModel):
    summary: str
    dimension_ids: list[str]
    estimable: bool
    reason: str | None = None


class AttributionView(BaseModel):
    verdict: str
    methodology: str
    limitation: str
    finding: str
    evidence_needed: str
    evidence_refs: list[str]
    diagnostic_refs: list[str] | None = Field(default=None, json_schema_extra=min_level("audit"))


class RecommendationView(BaseModel):
    id: str
    text: str
    rationale: str
    priority: int
    personas: list[str]
    evidence_refs: list[str]
    diagnostic_refs: list[str] | None = Field(default=None, json_schema_extra=min_level("audit"))


class AssessmentView(ProjectDataResponse):
    level: int
    level_name: str
    evidence_confidence: str
    simulated_banner: str | None = None
    observed_outcome: ConclusionView
    ecological_assessment: ConclusionView
    climate_adjusted_interpretation: ConclusionView
    comparative_assessment: ConclusionView
    attribution: AttributionView
    dimensions: list[DimensionView]
    recommendations: list[RecommendationView]
