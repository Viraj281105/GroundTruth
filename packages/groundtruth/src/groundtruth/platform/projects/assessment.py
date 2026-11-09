"""Gather real project artifacts and hand them to the pure assessment engine.

Every input is read from a provenance-checked cache, the stored boundary file or computed
readiness. Nothing is typed in by a caller and nothing is invented: a missing artifact becomes an
absent input (``None``, an empty mapping or an empty list), which the engine reports as
``Insufficient evidence`` with the reason. This module never raises for missing or corrupt data.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform, unary_union

from groundtruth.data_access.aoi_pipeline import AnnualObservationRecord
from groundtruth.engine import (
    Assessment,
    AssessmentInputs,
    ClimateYear,
    ReadinessSummary,
    SeriesPoint,
    SpreadPoint,
    assess,
)
from groundtruth.platform.projects.boundary import _to_equal_area
from groundtruth.platform.projects.data import (
    load_climate,
    load_observations,
    load_unit_observations,
)
from groundtruth.platform.projects.readiness import (
    INDICATOR,
    ProjectReadiness,
    _boundary_file,
    _eligible_donors,
    compute_project_readiness,
)
from groundtruth.platform.store.models import ProjectRow

INDICATORS: tuple[str, ...] = ("ndvi", "evi", "nbr", "ndmi")
"""Indicators cached for a project; each present one becomes one series."""

_UNOBSERVED = "UNAVAILABLE"


# --- series ----------------------------------------------------------------------------------


def dedupe_years(
    records: Iterable[AnnualObservationRecord],
) -> list[AnnualObservationRecord]:
    """One record per year: the one with the most valid pixels (never an average).

    Ties keep the first record seen, so the result is deterministic. Sorted by year.
    """
    best: dict[int, AnnualObservationRecord] = {}
    for rec in records:
        cur = best.get(rec.year)
        if cur is None or (rec.n_valid_pixels or 0) > (cur.n_valid_pixels or 0):
            best[rec.year] = rec
    return [best[y] for y in sorted(best)]


def _usable(records: Iterable[AnnualObservationRecord]) -> list[AnnualObservationRecord]:
    """Observed, finite-valued, de-duplicated records."""
    observed = [
        r for r in records if r.evidence_state != _UNOBSERVED and math.isfinite(float(r.value))
    ]
    return dedupe_years(observed)


def _ref(unit: str, indicator: str, rec: AnnualObservationRecord) -> str:
    return f"observation:{unit}:{indicator}:{rec.year}"


def _points(unit: str, indicator: str, records: Sequence[AnnualObservationRecord]) -> list[Any]:
    return [
        SeriesPoint(
            year=r.year,
            value=float(r.value),
            n_valid_pixels=int(r.n_valid_pixels or 0),
            evidence_refs=(_ref(unit, indicator, r),),
        )
        for r in records
    ]


def _spread(
    unit: str, indicator: str, records: Sequence[AnnualObservationRecord]
) -> list[SpreadPoint]:
    out: list[SpreadPoint] = []
    for r in records:
        zs = (r.processing_metadata or {}).get("zonal_stats")
        if not isinstance(zs, Mapping):
            continue
        p10, p90, std = zs.get("p10"), zs.get("p90"), zs.get("std")
        if not (
            isinstance(p10, int | float)
            and isinstance(p90, int | float)
            and isinstance(std, int | float)
            and all(math.isfinite(v) for v in (p10, p90, std))
        ):
            continue
        out.append(
            SpreadPoint(
                year=r.year,
                p10=float(p10),
                p90=float(p90),
                std=float(std),
                n_valid_pixels=int(zs.get("n_valid") or r.n_valid_pixels or 0),
                evidence_refs=(_ref(unit, indicator, r),),
            )
        )
    return out


# --- coverage --------------------------------------------------------------------------------


def _read_boundary(project: ProjectRow) -> BaseGeometry | None:
    """The project boundary as a lon/lat geometry, or ``None`` if it cannot be read."""
    if not project.boundary_path:
        return None
    file = _boundary_file(project.boundary_path)
    if file is None:
        return None
    try:
        doc = json.loads(file.read_text(encoding="utf-8"))
        if doc.get("type") == "FeatureCollection":
            geoms = [shape(f["geometry"]) for f in doc["features"]]
        elif doc.get("type") == "Feature":
            geoms = [shape(doc["geometry"])]
        else:
            geoms = [shape(doc)]
        geom = unary_union(geoms)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None
    if geom.is_empty or geom.geom_type not in ("Polygon", "MultiPolygon"):
        return None
    return geom


def boundary_area_m2(boundary: BaseGeometry) -> float:
    """Equal-area (EPSG:6933) area of the lon/lat boundary in square metres."""
    return float(transform(_to_equal_area().transform, boundary).area)


def grid_resolution_m(parameters: Mapping[str, Any] | None) -> float | None:
    """Pixel size from ``raster_grid.resolution_m``, else the first scene's ``resolution_m``."""
    params = parameters or {}
    grid = params.get("raster_grid")
    candidates: list[Any] = [grid.get("resolution_m") if isinstance(grid, Mapping) else None]
    scenes = params.get("scenes_metadata")
    if isinstance(scenes, Sequence) and not isinstance(scenes, str):
        candidates.extend(sc.get("resolution_m") for sc in scenes if isinstance(sc, Mapping))
    for value in candidates:
        if isinstance(value, int | float) and math.isfinite(value) and value > 0:
            return float(value)
    return None


def coverage_by_year(
    boundary: BaseGeometry,
    resolution_m: float | None,
    records: Sequence[AnnualObservationRecord],
) -> dict[int, float]:
    """Per-year share of the project AOI actually observed, in percent.

    ``n_valid_pixels`` counts clear pixels inside the AOI polygon on the processed grid, so
    coverage is ``n_valid_pixels * resolution_m**2 / polygon area``. It never falls back to
    ``clear_pixel_fraction`` or the bbox; unknown resolution or area gives an empty mapping.
    """
    if resolution_m is None or resolution_m <= 0:
        return {}
    area = boundary_area_m2(boundary)
    if area <= 0.0:
        return {}
    return {
        r.year: min(100.0, r.n_valid_pixels * resolution_m**2 / area * 100.0)
        for r in records
        if r.n_valid_pixels is not None
    }


# --- readiness mapping ------------------------------------------------------------------------


def _readiness_summary(readiness: ProjectReadiness, *, provenance_ok: bool) -> ReadinessSummary:
    by_id = {c.id: c for c in readiness.criteria}

    def met(cid: str) -> bool:
        view = by_id.get(cid)
        return view is not None and view.status == "met"

    climate = by_id.get("climate_coverage")
    missing: tuple[str, ...] = ()
    if (
        climate is not None
        and climate.status == "not_met"
        and isinstance(climate.observed_value, list)
    ):
        missing = tuple(str(m) for m in climate.observed_value)
    return ReadinessSummary(
        attribution_ready=readiness.attribution_ready,
        pre_treatment_observed=met("pre_treatment_observations"),
        donor_panel_available=met("donor_panel"),
        boundary_verified=met("boundary_verified"),
        climate_missing_months=missing,
        provenance_ok=provenance_ok,
        # No completed real-data causal run exists today (AGENTS.md section 9).
        causal_run_completed=False,
    )


# --- assembly ---------------------------------------------------------------------------------


def _climate_years(project: ProjectRow, data_dir: Path) -> list[ClimateYear] | None:
    result = load_climate(project, data_dir=data_dir)
    if result.status != "available" or result.bundle is None:
        return None
    case = result.bundle.case_id
    years = [
        ClimateYear(
            year=rec.year,
            rainfall_mm=rec.annual_rainfall_mm,
            spi12=rec.spi_12,
            temperature_c=rec.mean_temp_c,
            evidence_refs=(f"climate:{case}:{rec.year}",),
        )
        for rec in sorted(result.bundle.treated_summary.record_by_year().values(), key=_year_of)
    ]
    return years or None


def _year_of(rec: Any) -> int:
    return int(rec.year)


def _reference_series(
    project: ProjectRow, data_dir: Path, indicators: Iterable[str]
) -> dict[str, dict[str, list[Any]]] | None:
    """Donor vegetation series from cached donor observations; ``None`` when there are none."""
    donors = _eligible_donors(project, _cases_dir())
    if not donors:
        return None
    out: dict[str, dict[str, list[Any]]] = {}
    for ind in indicators:
        per: dict[str, list[Any]] = {}
        for donor in donors:
            unit = donor.get("unit_id")
            if not isinstance(unit, str):
                continue
            res = load_unit_observations(unit, ind, data_dir=data_dir)
            if res.status != "available" or res.bundle is None:
                continue
            pts = _points(unit, ind, _usable(res.bundle.records))
            if pts:
                per[unit] = pts
        if per:
            out[ind] = per
    return out or None


def _cases_dir() -> Path:
    from groundtruth.platform.config import get_settings

    return get_settings().cases_dir


def build_project_assessment(project: ProjectRow, *, data_dir: Path) -> Assessment:
    """Assess ``project`` from the real artifacts under ``data_dir``.

    A project with no case, no caches or a corrupt cache still yields a valid ``Assessment``
    (Level 0, "Not assessable") whose dimensions state what is missing. A simulated project
    gets whatever its loaders give (normally nothing) and is labelled by the engine; no series is
    ever fabricated here.
    """
    series: dict[str, list[Any]] = {}
    spread: dict[str, list[SpreadPoint]] = {}
    sensors: dict[int, list[str]] = {}
    coverage: dict[int, float] = {}
    boundary = _read_boundary(project)
    unit = project.case_id or project.slug
    any_bundle = False

    for ind in INDICATORS:
        res = load_observations(project, ind, data_dir=data_dir)
        if res.status != "available" or res.bundle is None:
            continue
        any_bundle = True
        records = _usable(res.bundle.records)
        pts = _points(unit, ind, records)
        if pts:
            series[ind] = pts
        sp = _spread(unit, ind, records)
        if sp:
            spread[ind] = sp
        if (ind == INDICATOR or not coverage) and boundary is not None and records:
            coverage = coverage_by_year(
                boundary, grid_resolution_m(res.bundle.provenance.parameters), records
            )
        for r in records:
            names = sensors.setdefault(r.year, [])
            if r.sensor not in names:
                names.append(r.sensor)

    readiness = compute_project_readiness(project, data_dir=data_dir)
    summary = _readiness_summary(readiness, provenance_ok=True)
    inputs = AssessmentInputs(
        series=series,
        zonal_spread=spread or None,
        climate=_climate_years(project, data_dir),
        reference_series=_reference_series(project, data_dir, series) if any_bundle else None,
        readiness=summary,
        coverage_pct=coverage,
        sensors=sensors,
        field_evidence=False,
        treatment_start_year=project.treatment_start_year,
        data_mode="simulated" if project.data_mode == "simulated" else "observed",
        zone_series=None,
    )
    return assess(inputs)
