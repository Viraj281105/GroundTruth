"""Donor eligibility matrix and (real-data-only) SCM conditioning diagnostics for Kariba.

Evaluates:
1. Spatial eligibility and SUTVA compliance, taken from the committed, geoBoundaries-
   derived ``cases/boundaries/kariba-donors.geojson`` (areas, distances, exclusions).
2. Climate summaries per donor from the real CHIRPS / NASA POWER cache.
3. Numerical matrix properties (rank, condition number, collinearity, SCM weights,
   pre-treatment fit, climate balance, leave-one-out stability) -- **only** when a real
   pre-treatment outcome panel is supplied.

GroundTruth Golden Rules enforced:
- Never report matrix diagnostics computed on simulated data. Without a real
  pre-treatment outcome panel the diagnostics are ``None`` (UNAVAILABLE).
- Missing outcome observations are never imputed: a NaN in the panel is refused.
- If the donor matrix is ill-conditioned or climate balance is inadequate,
  the causal result must remain INCONCLUSIVE.

Core vs caveat split (audit finding P1-3), derived from GeoJSON properties with the
pre-registered rules in :func:`classify_eligible_donor`:

- BORDER_LEAKAGE_CAVEAT: the unit shares a boundary with a host district
  (``host_adjacent_outside_buffer``), lies < 25 km from the project boundary, or lies
  < 10 km from a host district. Such units sit outside the 10 km exclusion belt but are
  the most exposed to activity displacement, so they are reserved for sensitivity analysis.
- HIGH_AGRICULTURAL_CAVEAT: **not assigned.** No land-use / cropland layer is attached to
  the donor units, so agricultural pressure cannot be screened. This is an open data gap,
  not evidence that the core units are free of agricultural modification.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import numpy as np

from groundtruth.contracts.errors import DataUnavailableError, InsufficientDataError
from groundtruth.engine.causal.synthetic_control import solve_simplex_least_squares

SMD_BALANCE_THRESHOLD = 0.25
PRE_RMSPE_THRESHOLD = 0.05
CONDITION_NUMBER_THRESHOLD = 1e5
_WEIGHT_EPS = 1e-6


class DonorCategory(StrEnum):
    """Eligibility classification for candidate donor units."""

    CORE_ELIGIBLE = "CORE_ELIGIBLE"
    BORDER_LEAKAGE_CAVEAT = "BORDER_LEAKAGE_CAVEAT"
    HIGH_AGRICULTURAL_CAVEAT = "HIGH_AGRICULTURAL_CAVEAT"
    SPATIALLY_EXCLUDED = "SPATIALLY_EXCLUDED"


@dataclass(frozen=True)
class DonorUnitAuditRecord:
    """Multi-attribute audit for a single candidate donor unit."""

    unit_id: str
    official_name: str
    country_iso3: str
    area_km2: float | None
    category: DonorCategory
    is_admitted_to_primary_pool: bool
    exclusion_or_caveat_reason: str | None
    provenance_source: str
    has_valid_geometry: bool
    distance_to_project_km: float | None
    distance_to_host_district_km: float | None
    pre_treatment_mean_rainfall_mm: float | None
    rainfall_difference_to_kariba_mm: float | None
    spi_drought_frequency: int | None
    mean_temp_c: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize audit record to dictionary."""
        return {
            "unit_id": self.unit_id,
            "official_name": self.official_name,
            "country_iso3": self.country_iso3,
            "area_km2": self.area_km2,
            "category": self.category.value,
            "is_admitted_to_primary_pool": self.is_admitted_to_primary_pool,
            "exclusion_or_caveat_reason": self.exclusion_or_caveat_reason,
            "provenance_source": self.provenance_source,
            "has_valid_geometry": self.has_valid_geometry,
            "distance_to_project_km": self.distance_to_project_km,
            "distance_to_host_district_km": self.distance_to_host_district_km,
            "pre_treatment_mean_rainfall_mm": self.pre_treatment_mean_rainfall_mm,
            "rainfall_difference_to_kariba_mm": self.rainfall_difference_to_kariba_mm,
            "spi_drought_frequency": self.spi_drought_frequency,
            "mean_temp_c": self.mean_temp_c,
        }


@dataclass(frozen=True)
class DonorMatrixDiagnostics:
    """Numerical conditioning and stability metrics for a *real* pre-treatment donor matrix."""

    matrix_shape: tuple[int, int]
    matrix_rank: int
    condition_number: float
    is_rank_deficient: bool
    is_ill_conditioned: bool
    max_pairwise_correlation: float
    weights: Mapping[str, float]
    effective_donors_count: float
    max_weight_concentration: float
    pre_treatment_rmspe: float
    climate_smd: float | None
    is_covariate_balanced: bool | None
    leave_one_out_max_impact: float
    solver_converged: bool
    is_numerically_feasible: bool
    verdict: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize matrix diagnostics to dictionary."""
        return {
            "matrix_shape": list(self.matrix_shape),
            "matrix_rank": self.matrix_rank,
            "condition_number": (
                "inf" if math.isinf(self.condition_number) else round(self.condition_number, 2)
            ),
            "is_rank_deficient": self.is_rank_deficient,
            "is_ill_conditioned": self.is_ill_conditioned,
            "max_pairwise_correlation": round(self.max_pairwise_correlation, 4),
            "weights": {k: round(v, 6) for k, v in self.weights.items()},
            "effective_donors_count": round(self.effective_donors_count, 2),
            "max_weight_concentration": round(self.max_weight_concentration, 4),
            "pre_treatment_rmspe": round(self.pre_treatment_rmspe, 5),
            "climate_smd": None if self.climate_smd is None else round(self.climate_smd, 4),
            "is_covariate_balanced": self.is_covariate_balanced,
            "leave_one_out_max_impact": round(self.leave_one_out_max_impact, 5),
            "solver_converged": self.solver_converged,
            "is_numerically_feasible": self.is_numerically_feasible,
            "verdict": self.verdict,
        }


@dataclass(frozen=True)
class DonorEligibilityAssessment:
    """Complete donor pool evaluation report for Kariba REDD+."""

    total_candidates_evaluated: int
    spatially_excluded_count: int
    spatially_eligible_count: int
    core_admitted_count: int
    border_caveat_count: int
    agricultural_caveat_count: int
    units: tuple[DonorUnitAuditRecord, ...]
    diagnostics: DonorMatrixDiagnostics | None
    diagnostics_status: str
    recommendation: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize assessment to dictionary."""
        return {
            "total_candidates_evaluated": self.total_candidates_evaluated,
            "spatially_excluded_count": self.spatially_excluded_count,
            "spatially_eligible_count": self.spatially_eligible_count,
            "core_admitted_count": self.core_admitted_count,
            "border_caveat_count": self.border_caveat_count,
            "agricultural_caveat_count": self.agricultural_caveat_count,
            "units": [u.to_dict() for u in self.units],
            "diagnostics": None if self.diagnostics is None else self.diagnostics.to_dict(),
            "diagnostics_status": self.diagnostics_status,
            "recommendation": self.recommendation,
        }


# --------------------------------------------------------------------------------------
# Real-panel diagnostics
# --------------------------------------------------------------------------------------


def _synthetic_path(donors: np.ndarray, treated: np.ndarray) -> tuple[np.ndarray, np.ndarray, bool]:
    weights, _, converged = solve_simplex_least_squares(donors, treated)
    return weights, donors @ weights, converged


def compute_donor_matrix_diagnostics(
    donor_ids: Sequence[str],
    donors_pre: np.ndarray,
    treated_pre: np.ndarray,
    *,
    donor_rainfall_mm: Sequence[float] | None = None,
    treated_rainfall_mm: float | None = None,
) -> DonorMatrixDiagnostics:
    """Compute SCM conditioning diagnostics from a real ``(T0, J)`` pre-treatment panel.

    Args:
        donor_ids: Donor identifiers, one per column of ``donors_pre``.
        donors_pre: ``(T0, J)`` observed pre-treatment donor outcomes.
        treated_pre: ``(T0,)`` observed pre-treatment treated outcome.
        donor_rainfall_mm: Optional per-donor pre-treatment rainfall for climate SMD.
        treated_rainfall_mm: Treated unit pre-treatment rainfall for climate SMD.

    Leave-one-out impact is the largest RMS change in the fitted pre-treatment synthetic
    path when any single positively weighted donor is dropped and weights are re-fitted.

    Raises:
        InsufficientDataError: on shape mismatch, too few periods/donors, or any
            non-finite observation (missing data is refused, never imputed).
    """
    donors = np.asarray(donors_pre, dtype=float)
    treated = np.asarray(treated_pre, dtype=float)
    if donors.ndim != 2 or treated.ndim != 1:
        raise InsufficientDataError("donors_pre must be 2-D (T0, J) and treated_pre 1-D (T0,)")
    t0, n_donors = donors.shape
    if treated.shape[0] != t0:
        raise InsufficientDataError(f"treated_pre has {treated.shape[0]} periods, donors_pre {t0}")
    if len(donor_ids) != n_donors:
        raise InsufficientDataError(f"{len(donor_ids)} donor ids for {n_donors} donor columns")
    if t0 < 2 or n_donors < 2:
        raise InsufficientDataError(f"Need at least 2 periods and 2 donors (got {t0}x{n_donors})")
    if not (np.all(np.isfinite(donors)) and np.all(np.isfinite(treated))):
        raise InsufficientDataError(
            "Pre-treatment panel contains missing/non-finite observations; "
            "refusing to impute. Drop the affected units or periods explicitly."
        )

    s_vals = np.linalg.svd(donors, compute_uv=False)
    cond = float(s_vals[0] / s_vals[-1]) if s_vals[-1] > 1e-12 else float("inf")
    rank = int(np.linalg.matrix_rank(donors))
    is_rank_def = rank < min(t0, n_donors)
    is_ill = bool(is_rank_def or cond > CONDITION_NUMBER_THRESHOLD)

    stds = donors.std(axis=0)
    varying = stds > 1e-12
    if varying.sum() >= 2:
        c_mat = np.corrcoef(donors[:, varying], rowvar=False)
        np.fill_diagonal(c_mat, 0.0)
        max_corr = float(np.nanmax(np.abs(c_mat)))
    else:
        max_corr = float("nan")

    weights, synth, converged = _synthetic_path(donors, treated)
    rmspe = float(np.sqrt(np.mean((treated - synth) ** 2)))
    eff_n = float(1.0 / np.sum(weights**2))
    max_w = float(np.max(weights))

    loo_impacts: list[float] = []
    for j in np.flatnonzero(weights > _WEIGHT_EPS):
        keep = np.arange(n_donors) != j
        _, synth_loo, _ = _synthetic_path(donors[:, keep], treated)
        loo_impacts.append(float(np.sqrt(np.mean((synth_loo - synth) ** 2))))
    loo_max = max(loo_impacts, default=0.0)

    smd: float | None = None
    balanced: bool | None = None
    if donor_rainfall_mm is not None and treated_rainfall_mm is not None:
        rain = np.asarray(donor_rainfall_mm, dtype=float)
        if rain.shape != (n_donors,) or not np.all(np.isfinite(rain)):
            raise InsufficientDataError("donor_rainfall_mm must be finite with one value per donor")
        rain_sd = float(np.std(rain, ddof=1))
        smd = abs(treated_rainfall_mm - float(rain @ weights)) / rain_sd if rain_sd > 0 else 0.0
        balanced = bool(smd <= SMD_BALANCE_THRESHOLD)

    feasible = bool(
        not is_ill and converged and rmspe <= PRE_RMSPE_THRESHOLD and (balanced is not False)
    )
    verdict = (
        "NUMERICALLY_FEASIBLE: the donor matrix is well-conditioned and the pre-period fit is "
        "within threshold. This does not by itself establish a valid counterfactual."
        if feasible
        else "NOT_FEASIBLE: conditioning, convergence, pre-period fit or climate balance fails; "
        "the causal result must remain INCONCLUSIVE."
    )
    return DonorMatrixDiagnostics(
        matrix_shape=(t0, n_donors),
        matrix_rank=rank,
        condition_number=cond,
        is_rank_deficient=is_rank_def,
        is_ill_conditioned=is_ill,
        max_pairwise_correlation=max_corr,
        weights={str(d): float(w) for d, w in zip(donor_ids, weights, strict=True)},
        effective_donors_count=eff_n,
        max_weight_concentration=max_w,
        pre_treatment_rmspe=rmspe,
        climate_smd=smd,
        is_covariate_balanced=balanced,
        leave_one_out_max_impact=loo_max,
        solver_converged=bool(converged),
        is_numerically_feasible=feasible,
        verdict=verdict,
    )


# --------------------------------------------------------------------------------------
# Kariba eligibility matrix
# --------------------------------------------------------------------------------------

# Pre-registered border-caveat thresholds (see module docstring). The GeoJSON already
# excludes units inside the 10 km leakage belt; these define a wider sensitivity tier.
BORDER_CAVEAT_MAX_PROJECT_DISTANCE_KM = 25.0
BORDER_CAVEAT_MAX_HOST_DISTANCE_KM = 10.0
_HOST_ADJACENT_CLASS = "host_adjacent_outside_buffer"


def classify_eligible_donor(props: Mapping[str, Any]) -> tuple[DonorCategory, str | None]:
    """Classify a spatially eligible unit as core or border caveat from its GeoJSON properties.

    A missing distance is treated as a caveat, never as "far away".
    """
    reasons: list[str] = []
    host_adjacent = props.get("spatial_classification") == _HOST_ADJACENT_CLASS
    if host_adjacent:
        reasons.append("shares a boundary with a host district")
    d_proj = props.get("distance_to_project_km")
    d_host = props.get("distance_to_host_district_km")
    if d_proj is None:
        reasons.append("distance to project unknown")
    elif float(d_proj) < BORDER_CAVEAT_MAX_PROJECT_DISTANCE_KM:
        reasons.append(
            f"distance to project {d_proj} km < {BORDER_CAVEAT_MAX_PROJECT_DISTANCE_KM:g} km"
        )
    if d_host is None:
        reasons.append("distance to host district unknown")
    elif float(d_host) < BORDER_CAVEAT_MAX_HOST_DISTANCE_KM and not host_adjacent:
        # A host-adjacent unit is 0 km from a host district by definition; said once above.
        reasons.append(
            f"distance to host district {d_host} km < {BORDER_CAVEAT_MAX_HOST_DISTANCE_KM:g} km"
        )
    if reasons:
        return (
            DonorCategory.BORDER_LEAKAGE_CAVEAT,
            "Leakage-exposure caveat (" + "; ".join(reasons) + "); sensitivity analysis only",
        )
    return DonorCategory.CORE_ELIGIBLE, None


def _default_donor_geojson_path() -> Path:
    from groundtruth.platform.config import REPO_ROOT

    return REPO_ROOT / "cases" / "boundaries" / "kariba-donors.geojson"


def _opt_float(value: Any) -> float | None:
    return None if value is None else float(value)


def build_kariba_donor_eligibility_matrix(
    *,
    climate_bundle: Any | None = None,
    donor_geojson_path: Path | str | None = None,
    pre_treatment_panel: Mapping[str, Sequence[float]] | None = None,
    treated_pre_series: Sequence[float] | None = None,
) -> DonorEligibilityAssessment:
    """Build the Kariba REDD+ donor eligibility matrix from committed boundary data.

    Spatial classification, areas and distances come from the donor GeoJSON. Matrix
    diagnostics are computed **only** if a real pre-treatment outcome panel is supplied:

    Args:
        climate_bundle: Real climate bundle (loaded from the default cache if ``None``).
        donor_geojson_path: Override for ``cases/boundaries/kariba-donors.geojson``.
        pre_treatment_panel: ``{donor_id: [T0 observed outcomes]}`` covering every core donor.
        treated_pre_series: ``[T0 observed outcomes]`` for the treated unit.

    Raises:
        DataUnavailableError: if the donor GeoJSON is missing, or the supplied panel does
            not cover every core donor.
    """
    if climate_bundle is None:
        from groundtruth.data_access.climate import (
            DEFAULT_CLIMATE_CACHE_PATH,
            load_kariba_climate_bundle,
        )

        climate_bundle = load_kariba_climate_bundle(DEFAULT_CLIMATE_CACHE_PATH)

    geo_path = Path(donor_geojson_path) if donor_geojson_path else _default_donor_geojson_path()
    if not geo_path.is_file():
        raise DataUnavailableError(f"Donor boundary GeoJSON not found at {geo_path}")
    features = json.loads(geo_path.read_text(encoding="utf-8")).get("features", [])

    kariba_rainfall = climate_bundle.treated_summary.pre_treatment_mean_rainfall_mm
    units_audit: list[DonorUnitAuditRecord] = []

    for feat in features:
        p = feat.get("properties") or {}
        uid = str(p.get("unit_id"))
        eligible = bool(p.get("eligible_for_donor_pool"))
        c_summary = climate_bundle.unit_summaries.get(uid)
        rain = None if c_summary is None else c_summary.pre_treatment_mean_rainfall_mm

        if not eligible:
            cat, admitted = DonorCategory.SPATIALLY_EXCLUDED, False
            reason = p.get("exclusion_reason") or str(p.get("spatial_classification"))
        else:
            cat, reason = classify_eligible_donor(p)
            admitted = cat == DonorCategory.CORE_ELIGIBLE

        units_audit.append(
            DonorUnitAuditRecord(
                unit_id=uid,
                official_name=str(p.get("official_name", uid)),
                country_iso3=str(p.get("country_iso3", "")),
                area_km2=_opt_float(p.get("area_km2")),
                category=cat,
                is_admitted_to_primary_pool=admitted,
                exclusion_or_caveat_reason=reason,
                provenance_source=str(p.get("source_version", "unknown")),
                has_valid_geometry=bool(
                    p.get("verified_geometry", feat.get("geometry") is not None)
                ),
                distance_to_project_km=_opt_float(p.get("distance_to_project_km")),
                distance_to_host_district_km=_opt_float(p.get("distance_to_host_district_km")),
                pre_treatment_mean_rainfall_mm=None if rain is None else round(rain, 1),
                rainfall_difference_to_kariba_mm=(
                    None
                    if rain is None or kariba_rainfall is None
                    else round(rain - kariba_rainfall, 1)
                ),
                spi_drought_frequency=(
                    None if c_summary is None else len(c_summary.pre_treatment_drought_years)
                ),
                mean_temp_c=None if c_summary is None else c_summary.baseline_mean_temp_c,
            )
        )

    core = [u for u in units_audit if u.is_admitted_to_primary_pool]
    count = lambda c: sum(1 for u in units_audit if u.category == c)  # noqa: E731

    diagnostics: DonorMatrixDiagnostics | None = None
    if pre_treatment_panel is None or treated_pre_series is None:
        status = (
            "UNAVAILABLE: no real pre-treatment outcome panel was supplied, so rank, "
            "condition number, SCM weights, pre-RMSPE, climate SMD and leave-one-out "
            "stability are not reported."
        )
        recommendation = (
            "Acquire real pre-treatment outcome series for the treated unit and every core "
            "donor, then recompute diagnostics. Until then the causal result is not estimable."
        )
    else:
        missing = [u.unit_id for u in core if u.unit_id not in pre_treatment_panel]
        if missing:
            raise DataUnavailableError(
                f"Pre-treatment panel lacks {len(missing)} core donor(s): {', '.join(missing)}"
            )
        donor_ids = [u.unit_id for u in core]
        donors_pre = np.column_stack([np.asarray(pre_treatment_panel[d], float) for d in donor_ids])
        rains = [u.pre_treatment_mean_rainfall_mm for u in core]
        have_rain = kariba_rainfall is not None and all(r is not None for r in rains)
        diagnostics = compute_donor_matrix_diagnostics(
            donor_ids,
            donors_pre,
            np.asarray(treated_pre_series, float),
            donor_rainfall_mm=[float(r) for r in rains if r is not None] if have_rain else None,
            treated_rainfall_mm=kariba_rainfall if have_rain else None,
        )
        status = "COMPUTED from the supplied observed pre-treatment panel."
        recommendation = (
            "Use the core donors for primary SCM estimation and the caveat donors for "
            "sensitivity analysis; numerical feasibility does not establish identification."
        )

    return DonorEligibilityAssessment(
        total_candidates_evaluated=len(units_audit),
        spatially_excluded_count=count(DonorCategory.SPATIALLY_EXCLUDED),
        spatially_eligible_count=len(units_audit) - count(DonorCategory.SPATIALLY_EXCLUDED),
        core_admitted_count=len(core),
        border_caveat_count=count(DonorCategory.BORDER_LEAKAGE_CAVEAT),
        agricultural_caveat_count=count(DonorCategory.HIGH_AGRICULTURAL_CAVEAT),
        units=tuple(units_audit),
        diagnostics=diagnostics,
        diagnostics_status=status,
        recommendation=recommendation,
    )


__all__ = [
    "DonorCategory",
    "DonorEligibilityAssessment",
    "DonorMatrixDiagnostics",
    "DonorUnitAuditRecord",
    "build_kariba_donor_eligibility_matrix",
    "classify_eligible_donor",
    "compute_donor_matrix_diagnostics",
]
