"""Computed project readiness: can causal attribution be attempted for this project?

Every number here is derived from a real artifact: the stored boundary file, the
provenance-checked observation cache, the ingested climate bundle and the donor screening
file. Nothing is typed in by a caller. A missing or corrupt artifact makes the criteria that
need it ``unavailable``; it never raises and never substitutes a default.

Readiness is one input to the assessment engine. It answers only "can attribution be
attempted?" (``attribution_ready``); it neither scores a project nor decides what is shown.

The quantitative causal checks (pre-treatment duration, donor-pool size, sensor
comparability) are evaluated by ``engine.causal.readiness.assess_causal_readiness`` so the
criterion logic lives in one place; this module only derives its inputs.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from groundtruth.data_access.aoi_pipeline import AnnualObservationRecord
from groundtruth.engine import CausalCriterionResult, assess_causal_readiness
from groundtruth.platform.config import get_settings
from groundtruth.platform.projects.data import (
    load_climate,
    load_observations,
    load_unit_observations,
)
from groundtruth.platform.store.models import ProjectRow

CriterionStatus = Literal["met", "not_met", "unavailable"]

INDICATOR = "ndvi"
"""The indicator readiness is judged on; the others are cached for the same units and years."""

OBSERVATION_YEARS_REQUIRED = 6
"""Observed years needed for any trend statement. Mirrors the assessment engine's provisional
minimum number of periods for a trend test; kept local so this module does not depend on the
engine's assessment rules."""

_UNOBSERVED = "UNAVAILABLE"
_MONTH_DOTTED = re.compile(r"^(\d{4})\.(\d{2})$")


@dataclass(frozen=True)
class CriterionView:
    """One readiness criterion as shown to a user."""

    id: str
    name: str
    status: CriterionStatus
    observed_value: Any
    required: Any
    evidence_needed: str


@dataclass(frozen=True)
class ProjectReadiness:
    """All readiness criteria for a project; ``attribution_ready`` only when every one is met."""

    criteria: list[CriterionView]
    attribution_ready: bool


@dataclass(frozen=True)
class _Donors:
    """Donor panel derived from the screening file and the observation cache."""

    status: Literal["available", "unavailable"]
    reason: str | None
    eligible: int
    usable: int
    independent: bool
    min_distance_km: float


# --- boundary --------------------------------------------------------------------------------


def _boundary_file(boundary_path: str) -> Path | None:
    """Locate the stored boundary file, or ``None`` when it does not exist.

    Absolute paths are used as they are. A relative path is the repository-relative style
    both the seed and uploads store (``cases/boundaries/...``), resolved against the directory
    above ``cases_dir``; failing that, the seed's own convention (the file name under
    ``cases_dir/boundaries``) is tried.
    """
    declared = Path(boundary_path)
    if declared.is_absolute():
        return declared if declared.is_file() else None
    cases_dir = get_settings().cases_dir
    for candidate in (cases_dir.parent / declared, cases_dir / "boundaries" / declared.name):
        if candidate.is_file():
            return candidate
    return None


def _boundary_view(project: ProjectRow) -> CriterionView:
    """Boundary present and verified.

    Two hash conventions exist: uploads hash the normalised GeoJSON bytes they store, and the
    seed hashes the raw repository file it points at. In both cases the recorded digest is of
    the bytes at ``boundary_path``, so this check hashes the stored file's bytes and compares.
    """
    name = "Project boundary verified"
    required = True
    if not project.boundary_path:
        return CriterionView(
            "boundary_verified",
            name,
            "not_met",
            False,
            required,
            "Upload the project boundary (GeoJSON polygon) so its area and extent can be verified.",
        )
    if not project.boundary_sha256:
        return CriterionView(
            "boundary_verified",
            name,
            "not_met",
            False,
            required,
            "No SHA-256 was recorded for the boundary; re-upload it so the file can be verified.",
        )
    file = _boundary_file(project.boundary_path)
    if file is None:
        return CriterionView(
            "boundary_verified",
            name,
            "not_met",
            False,
            required,
            "The recorded boundary file is missing from storage; upload it again.",
        )
    try:
        digest = hashlib.sha256(file.read_bytes()).hexdigest()
    except OSError:
        return CriterionView(
            "boundary_verified",
            name,
            "unavailable",
            None,
            required,
            "The boundary file could not be read; check storage permissions and retry.",
        )
    if digest != project.boundary_sha256.lower():
        return CriterionView(
            "boundary_verified",
            name,
            "not_met",
            False,
            required,
            "The boundary file no longer matches its recorded SHA-256; re-upload the "
            "boundary or restore the original file.",
        )
    return CriterionView("boundary_verified", name, "met", True, required, "")


# --- observations ----------------------------------------------------------------------------


def _observed(records: tuple[AnnualObservationRecord, ...]) -> list[AnnualObservationRecord]:
    """Records that carry a value; an empty (NaN) year is ``UNAVAILABLE`` and is not observed."""
    return [r for r in records if r.evidence_state != _UNOBSERVED]


NO_INGESTION_PATH = (
    "No satellite observations have been ingested for this project yet. Request them from the "
    "Earth observation tab: a GroundTruth worker downloads and processes Sentinel-2 scenes "
    "inside your boundary, and the request's status is shown there. You can upload project "
    "documents in the meantime."
)
"""Said when a project has no linked case and nothing ingested: the real state of that project."""


def _unavailable(
    cid: str, name: str, required: Any, reason: str | None, *, no_case: bool = False
) -> CriterionView:
    if no_case:
        needed = f"{reason}. {NO_INGESTION_PATH}" if reason else NO_INGESTION_PATH
    elif reason:
        needed = (
            f"{reason}. Ingest {INDICATOR} observations for this project "
            "to evaluate this criterion."
        )
    else:
        needed = f"Ingest {INDICATOR} observations for this project to evaluate this criterion."
    return CriterionView(cid, name, "unavailable", None, required, needed)


def _coverage_fraction(records: list[AnnualObservationRecord]) -> float:
    """Lowest observed-year AOI coverage as a fraction (0 when nothing was observed)."""
    if not records:
        return 0.0
    return min(
        (r.aoi_coverage_pct / 100.0) if r.aoi_coverage_pct is not None else r.clear_pixel_fraction
        for r in records
    )


# --- climate ---------------------------------------------------------------------------------


def normalise_month(month: str) -> str:
    """``2022.07`` (the cache's spelling) becomes ``2022-07``."""
    match = _MONTH_DOTTED.match(month)
    return f"{match.group(1)}-{match.group(2)}" if match else month


def _climate_view(project: ProjectRow, data_dir: Path) -> CriterionView:
    name = "Climate series complete"
    required = "no missing months"
    result = load_climate(project, data_dir=data_dir)
    if result.status != "available" or result.bundle is None:
        return CriterionView(
            "climate_coverage",
            name,
            "unavailable",
            None,
            required,
            f"{result.reason}. Ingest a monthly precipitation series covering the project "
            "to evaluate climate coverage.",
        )
    missing = sorted({normalise_month(m) for m in result.bundle.missing_months_after_upstream})
    if not missing:
        return CriterionView("climate_coverage", name, "met", [], required, "")
    return CriterionView(
        "climate_coverage",
        name,
        "not_met",
        missing,
        required,
        f"Backfill the missing months ({', '.join(missing)}) from an independent source, or "
        "document how the gaps were handled before relying on drought adjustment.",
    )


# --- donor panel -----------------------------------------------------------------------------


def _eligible_donors(project: ProjectRow, cases_dir: Path) -> list[dict[str, Any]] | None:
    """Eligible donor feature properties screened for ``project``'s case, ``None`` if corrupt.

    Screening files are ``cases/boundaries/*-donors.geojson`` whose features carry the case id
    they were screened for; a project with no such file simply has no screened donors.
    """
    eligible: list[dict[str, Any]] = []
    for file in sorted((cases_dir / "boundaries").glob("*-donors.geojson")):
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
            features = data["features"]
            for feature in features:
                props = feature["properties"]
                if props.get("case_id") == project.case_id and props.get("eligible_for_donor_pool"):
                    eligible.append(props)
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            return None
    return eligible


def _donor_panel(project: ProjectRow, data_dir: Path, observed_years: set[int]) -> _Donors:
    """Eligible donors that have cached observations for every year the project was observed."""
    props = _eligible_donors(project, get_settings().cases_dir)
    if props is None:
        return _Donors("unavailable", "The donor screening file is unreadable", 0, 0, True, 0.0)
    usable: list[dict[str, Any]] = []
    for donor in props:
        unit_id = donor.get("unit_id")
        if not isinstance(unit_id, str):
            continue
        result = load_unit_observations(unit_id, INDICATOR, data_dir=data_dir)
        if result.status != "available" or result.bundle is None:
            continue
        donor_years = {r.year for r in _observed(result.bundle.records)}
        if observed_years <= donor_years:
            usable.append(donor)
    independent = all(
        donor.get("overlaps_project_boundary") is False
        and donor.get("within_10km_leakage_belt") is False
        for donor in usable
    )
    distances = [
        float(d["distance_to_project_km"])
        for d in usable
        if isinstance(d.get("distance_to_project_km"), int | float)
    ]
    return _Donors(
        "available",
        None,
        len(props),
        len(usable),
        independent,
        min(distances) if distances else 0.0,
    )


# --- assembly --------------------------------------------------------------------------------


def _years_text(years: list[int]) -> str:
    if not years:
        return "no observed year"
    return f"{years[0]}-{years[-1]}" if len(years) > 1 else str(years[0])


def compute_project_readiness(project: ProjectRow, *, data_dir: Path) -> ProjectReadiness:
    """Derive every readiness criterion for ``project`` from the artifacts under ``data_dir``.

    ``attribution_ready`` is true only when all six criteria are met. Never raises for missing
    or corrupt caches: those criteria are ``unavailable`` with the reason and next step.
    """
    boundary = _boundary_view(project)
    climate = _climate_view(project, data_dir)
    obs = load_observations(project, INDICATOR, data_dir=data_dir)
    available = obs.status == "available" and obs.bundle is not None

    year_name = "Observed years"
    pre_name = "Pre-treatment observations"
    donor_name = "Donor panel available"
    sensor_name = "Sensor continuity"
    if not available or obs.bundle is None:
        reason = obs.reason
        nc = project.case_id is None
        views = [
            boundary,
            _unavailable(
                "observation_years", year_name, OBSERVATION_YEARS_REQUIRED, reason, no_case=nc
            ),
            _unavailable("pre_treatment_observations", pre_name, None, reason, no_case=nc),
            climate,
            _unavailable("donor_panel", donor_name, None, reason, no_case=nc),
            _unavailable("sensor_continuity", sensor_name, None, reason, no_case=nc),
        ]
        return ProjectReadiness(views, all(v.status == "met" for v in views))

    records = _observed(obs.bundle.records)
    years = sorted({r.year for r in records})
    start = project.treatment_start_year
    pre_years = [y for y in years if y < start]
    sensors = sorted({r.sensor for r in records})
    donors = _donor_panel(project, data_dir, set(years))

    # Engine inputs are all measured above. ``spillover_buffer_km`` is the realised distance to
    # the nearest usable donor; the engine does not use it in any criterion.
    report = assess_causal_readiness(
        case_id=project.case_id or project.slug,
        unit_id=project.case_id or project.slug,
        pre_treatment_years=len(pre_years),
        post_treatment_years=len(years) - len(pre_years),
        usable_donors_count=donors.usable,
        aoi_coverage_fraction=_coverage_fraction(records),
        donor_pool_independence=donors.independent,
        spillover_buffer_km=donors.min_distance_km,
        sensor_discontinuity_present=len(sensors) > 1,
    )
    engine: dict[str, CausalCriterionResult] = {c.criterion_id: c for c in report.criteria}

    obs_ok = len(years) >= OBSERVATION_YEARS_REQUIRED
    observed_years_view = CriterionView(
        "observation_years",
        year_name,
        "met" if obs_ok else "not_met",
        len(years),
        OBSERVATION_YEARS_REQUIRED,
        ""
        if obs_ok
        else f"Acquire annual {INDICATOR} observations for at least "
        f"{OBSERVATION_YEARS_REQUIRED} years ({len(years)} observed"
        f"{', ' + _years_text(years) if years else ''}).",
    )

    pre = engine["pre_treatment_duration"]
    pre_text = pre.evidence_needed
    if not pre.passed:
        first = f"Observations begin in {years[0]}" if years else "No year was observed"
        pre_text = f"{pre_text} {first}; treatment began in {start}."
    pre_view = CriterionView(
        "pre_treatment_observations",
        pre_name,
        "met" if pre.passed else "not_met",
        pre.observed_value,
        pre.threshold,
        pre_text,
    )

    pool = engine["donor_pool_size"]
    donor_view: CriterionView
    if donors.status == "unavailable":
        donor_view = CriterionView(
            "donor_panel",
            donor_name,
            "unavailable",
            None,
            pool.threshold,
            f"{donors.reason}. Restore the donor screening file to evaluate the donor panel.",
        )
    else:
        donor_text = pool.evidence_needed
        if not pool.passed:
            donor_text = (
                f"{donors.eligible} eligible donor units were screened for this project; "
                f"{donors.usable} have cached {INDICATOR} observations for "
                f"{_years_text(years)}. {donor_text}"
            )
        donor_view = CriterionView(
            "donor_panel",
            donor_name,
            "met" if pool.passed else "not_met",
            pool.observed_value,
            pool.threshold,
            donor_text,
        )

    sensor = engine["sensor_comparability"]
    sensor_view = CriterionView(
        "sensor_continuity",
        sensor_name,
        "met" if sensor.passed else "not_met",
        sensors,
        "one sensor, or a validated harmonisation across sensors",
        sensor.evidence_needed,
    )

    views = [boundary, observed_years_view, pre_view, climate, donor_view, sensor_view]
    return ProjectReadiness(views, all(v.status == "met" for v in views))
