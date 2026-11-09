"""Build the project data responses from provenance-checked artifacts.

Nothing here computes a number: it reshapes what the loaders, readiness and the assessment
adapter already produced. A missing or corrupt artifact is ``status: "unavailable"`` with the
loader's own reason; no value is ever invented or defaulted. Level-dependent fields are marked on
the response models and removed by ``redaction.redact``; the builders always fill every field.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from groundtruth.data_access.aoi_pipeline import AnnualObservationRecord
from groundtruth.engine import Assessment
from groundtruth.platform.api.project_schemas import (
    AssessmentView,
    AttributionView,
    ClimateSourceView,
    ClimateView,
    ClimateYearView,
    ConclusionView,
    DimensionView,
    EvidenceInventoryView,
    IndicatorInventory,
    InventoryItem,
    ObservationPoint,
    ObservationsView,
    ReadinessCriterion,
    ReadinessView,
    RecommendationView,
    StatusKind,
)
from groundtruth.platform.api.schemas import SIMULATED_NOTICE
from groundtruth.platform.projects.assessment import (
    INDICATORS,
    _read_boundary,
    coverage_by_year,
    grid_resolution_m,
)
from groundtruth.platform.projects.data import ClimateResult, load_climate, load_observations
from groundtruth.platform.projects.readiness import (
    ProjectReadiness,
    compute_project_readiness,
    normalise_month,
)
from groundtruth.platform.store.models import ProjectRow

PUBLIC_REF_PREFIXES: tuple[str, ...] = ("observation:", "climate:", "dimension:", "readiness:")
"""Evidence-ref kinds that point at observations, climate or other dimensions. Any other ref
(a causal-run evidence id, say) points into diagnostics and is audit-level."""


def data_mode_of(project: ProjectRow) -> str:
    return "simulated" if project.data_mode == "simulated" else "observed"


def simulated_warnings(project: ProjectRow, existing: Iterable[str] = ()) -> list[str]:
    """``existing`` plus the SIMULATED DATA notice when the project is simulated (R7)."""
    warnings = list(existing)
    if data_mode_of(project) == "simulated" and not any("SIMULATED DATA" in w for w in warnings):
        warnings.insert(0, SIMULATED_NOTICE)
    return warnings


# --- readiness -------------------------------------------------------------------------------


def readiness_fields(readiness: ProjectReadiness) -> dict[str, Any]:
    return {
        "attribution_ready": readiness.attribution_ready,
        "criteria": [
            ReadinessCriterion(
                id=c.id,
                name=c.name,
                status=c.status,
                observed_value=c.observed_value,
                required=c.required,
                evidence_needed=c.evidence_needed,
            )
            for c in readiness.criteria
        ],
    }


def build_readiness(project: ProjectRow, access_level: str, data_dir: Path) -> ReadinessView:
    return ReadinessView(
        data_mode=data_mode_of(project),  # type: ignore[arg-type]
        access_level=access_level,  # type: ignore[arg-type]
        **readiness_fields(compute_project_readiness(project, data_dir=data_dir)),
    )


# --- observations ----------------------------------------------------------------------------


def _finite(value: float) -> float | None:
    return float(value) if math.isfinite(float(value)) else None


def _points(
    project: ProjectRow, records: Iterable[AnnualObservationRecord], coverage: dict[int, float]
) -> list[ObservationPoint]:
    return [
        ObservationPoint(
            year=r.year,
            value=_finite(r.value),
            evidence_state=r.evidence_state,  # type: ignore[arg-type]
            sensor=r.sensor,
            clear_pixel_fraction=r.clear_pixel_fraction,
            n_scenes=r.n_scenes,
            aoi_coverage_pct=coverage.get(r.year),
            scene_ids=list(r.scene_ids),
            scenes_sha256=r.scenes_sha256,
        )
        for r in sorted(records, key=lambda rec: rec.year)
    ]


def _coverage(project: ProjectRow, bundle: Any) -> dict[int, float]:
    boundary = _read_boundary(project)
    if boundary is None:
        return {}
    usable = [r for r in bundle.records if r.evidence_state != "UNAVAILABLE"]
    return coverage_by_year(boundary, grid_resolution_m(bundle.provenance.parameters), usable)


def build_observations(
    project: ProjectRow, indicator: str, access_level: str, data_dir: Path
) -> ObservationsView:
    result = load_observations(project, indicator, data_dir=data_dir)
    common: dict[str, Any] = {
        "data_mode": data_mode_of(project),
        "access_level": access_level,
        "indicator": indicator,
    }
    if result.status != "available" or result.bundle is None:
        return ObservationsView(status="unavailable", reason=result.reason, **common)
    bundle = result.bundle
    return ObservationsView(
        status="available",
        unit_id=bundle.unit_id,
        source=bundle.provenance.source,
        points=_points(project, bundle.records, _coverage(project, bundle)),
        **common,
    )


# --- climate ---------------------------------------------------------------------------------


def build_climate(project: ProjectRow, access_level: str, data_dir: Path) -> ClimateView:
    result: ClimateResult = load_climate(project, data_dir=data_dir)
    common: dict[str, Any] = {"data_mode": data_mode_of(project), "access_level": access_level}
    if result.status != "available" or result.bundle is None:
        return ClimateView(status="unavailable", reason=result.reason, **common)
    bundle = result.bundle
    summary = bundle.treated_summary
    return ClimateView(
        status="available",
        case_id=bundle.case_id,
        sources=[
            ClimateSourceView(
                name=name,
                dataset_id=s.dataset_id,
                provider=s.provider,
                citation=s.citation,
                temporal_coverage_start=s.temporal_coverage_start,
                temporal_coverage_end=s.temporal_coverage_end,
                known_coverage_gaps=list(s.known_coverage_gaps),
            )
            for name, s in bundle.sources.items()
        ],
        missing_months=sorted({normalise_month(m) for m in bundle.missing_months_after_upstream}),
        years=[
            ClimateYearView(
                year=r.year,
                valid_months=r.valid_months,
                is_complete_year=r.is_complete_year,
                annual_rainfall_mm=r.annual_rainfall_mm,
                rainfall_anomaly_mm=r.rainfall_anomaly_mm,
                rainfall_anomaly_z=r.rainfall_anomaly_z,
                spi_12=r.spi_12,
                drought_classification=r.drought_classification,
                mean_temp_c=r.mean_temp_c,
            )
            for r in sorted(summary.records, key=lambda rec: rec.year)
        ],
        bundle_sha256=bundle.sha256,
        **common,
    )


# --- evidence inventory ----------------------------------------------------------------------


def build_inventory(
    project: ProjectRow, access_level: str, data_dir: Path
) -> EvidenceInventoryView:
    indicators: list[IndicatorInventory] = []
    items: list[InventoryItem] = []
    totals: dict[str, int] = {}
    first_reason: str | None = None
    for ind in INDICATORS:
        res = load_observations(project, ind, data_dir=data_dir)
        if res.status != "available" or res.bundle is None:
            first_reason = first_reason or res.reason
            indicators.append(
                IndicatorInventory(indicator=ind, status="unavailable", reason=res.reason)  # type: ignore[arg-type]
            )
            continue
        records = sorted(res.bundle.records, key=lambda r: r.year)
        states: dict[str, int] = {}
        for r in records:
            states[r.evidence_state] = states.get(r.evidence_state, 0) + 1
            totals[r.evidence_state] = totals.get(r.evidence_state, 0) + 1
            items.append(
                InventoryItem(
                    indicator=ind,  # type: ignore[arg-type]
                    year=r.year,
                    n_scenes=r.n_scenes,
                    scene_ids=list(r.scene_ids),
                    scenes_sha256=r.scenes_sha256,
                )
            )
        indicators.append(
            IndicatorInventory(
                indicator=ind,  # type: ignore[arg-type]
                status="available",
                n_records=len(records),
                years=[r.year for r in records],
                states=states,
                sensors=sorted({r.sensor for r in records}),
                source=res.bundle.provenance.source,
                data_origin=str(res.bundle.data_origin.value),
            )
        )
    available = [i for i in indicators if i.status == "available"]
    climate = load_climate(project, data_dir=data_dir)
    kinds = ["observations"] if available else []
    if climate.status == "available":
        kinds.append("climate")
    if project.boundary_sha256:
        kinds.append("boundary")
    return EvidenceInventoryView(
        data_mode=data_mode_of(project),  # type: ignore[arg-type]
        access_level=access_level,  # type: ignore[arg-type]
        status="available" if available else "unavailable",
        reason=None if available else first_reason,
        kinds=kinds,
        indicators=indicators,
        states=totals,
        climate_status=climate.status,
        climate_reason=climate.reason,
        boundary_sha256=project.boundary_sha256,
        items=items,
    )


# --- assessment ------------------------------------------------------------------------------


def _status_kind(dimension_id: str) -> StatusKind:
    if dimension_id == "evidence_quality":
        return "quality_rating"
    if dimension_id == "intervention_attribution":
        return "attribution_verdict"
    return "trend_status"


def split_refs(refs: Iterable[str]) -> tuple[list[str], list[str]]:
    """``refs`` partitioned (order kept) into public refs and refs that point at diagnostics."""
    public: list[str] = []
    diagnostic: list[str] = []
    for ref in refs:
        (public if ref.startswith(PUBLIC_REF_PREFIXES) else diagnostic).append(ref)
    return public, diagnostic


def _conclusion(c: Any) -> ConclusionView:
    return ConclusionView(
        summary=c.summary,
        dimension_ids=list(c.dimension_ids),
        estimable=c.estimable,
        reason=c.reason,
    )


def build_assessment(
    assessment: Assessment, project: ProjectRow, access_level: str
) -> AssessmentView:
    dims = []
    for d in assessment.dimensions:
        public, diagnostic = split_refs(d.evidence_refs)
        dims.append(
            DimensionView(
                id=d.id,
                title=d.title,
                status=d.status,
                status_kind=_status_kind(d.id),
                finding=d.finding,
                known=list(d.known),
                suggested=list(d.suggested),
                cannot_establish=list(d.cannot_establish),
                limitation=d.limitation,
                evidence_needed=d.evidence_needed,
                confidence=d.confidence,
                evidence_refs=public,
                diagnostic_refs=diagnostic,
                facts=dict(d.facts),
            )
        )
    a = assessment.attribution
    a_public, a_diag = split_refs(a.evidence_refs)
    recs = []
    for r in assessment.recommendations:
        r_public, r_diag = split_refs(r.evidence_refs)
        recs.append(
            RecommendationView(
                id=r.id,
                text=r.text,
                rationale=r.rationale,
                priority=r.priority,
                personas=list(r.personas),
                evidence_refs=r_public,
                diagnostic_refs=r_diag,
            )
        )
    simulated = assessment.data_mode == "simulated" or data_mode_of(project) == "simulated"
    return AssessmentView(
        data_mode="simulated" if simulated else "observed",
        access_level=access_level,  # type: ignore[arg-type]
        level=assessment.level,
        level_name=assessment.level_name,
        evidence_confidence=assessment.evidence_confidence,
        simulated_banner=assessment.simulated_banner or (SIMULATED_NOTICE if simulated else None),
        observed_outcome=_conclusion(assessment.observed_outcome),
        ecological_assessment=_conclusion(assessment.ecological_assessment),
        climate_adjusted_interpretation=_conclusion(assessment.climate_adjusted_interpretation),
        comparative_assessment=_conclusion(assessment.comparative_assessment),
        attribution=AttributionView(
            verdict=a.verdict,
            methodology=a.methodology,
            limitation=a.limitation,
            finding=a.finding,
            evidence_needed=a.evidence_needed,
            evidence_refs=a_public,
            diagnostic_refs=a_diag,
        ),
        dimensions=dims,
        recommendations=recs,
    )
