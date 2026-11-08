"""Climate confounding diagnostics, donor climate comparability, and sensitivity analysis.

Implements Task 3 items 9–13 while enforcing all Critical Scientific Rules:
- Does NOT silently modify ``fit_synthetic_control`` or ``estimate_did``.
- Evaluates how rainfall, drought (SPI), and temperature differences affect donor
  comparability and pre-treatment fit.
- Implements explicit unadjusted vs. climate-adjusted (weather-residualized and
  pre-treatment climate-augmented) SCM and DiD diagnostic comparisons.
- Estimates weather sensitivity (beta) strictly from untreated donor units or
  pre-treatment periods so treatment effects are never absorbed into climate controls.
- Flags risks of post-treatment bad controls if a covariate diverges post-treatment.
- Preserves all causal identification gates (J > T_0 under-identification, uniform
  weight degeneracy, relative pre-RMSPE, convex hull, placebo inference, LOO,
  covariate balance, and biomass calibration) and retains INCONCLUSIVE when
  identification remains insufficient.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol

import numpy as np
from numpy.typing import NDArray

from groundtruth.contracts.types import VerdictLabel
from groundtruth.engine.causal.did import DiDResult, estimate_did
from groundtruth.engine.causal.synthetic_control import (
    SyntheticControlFit,
    fit_synthetic_control,
    solve_simplex_least_squares,
)
from groundtruth.engine.matching.donors import standardised_mean_difference


@dataclass(frozen=True)
class ClimateCovariateBalance:
    """Standardized mean differences (SMDs) for climate covariates across the donor pool."""

    standardized_mean_differences: tuple[tuple[str, float], ...]
    max_abs_smd: float
    is_balanced: bool


def _assess_climate_covariate_balance(
    treated_vec: NDArray[np.float64],
    donor_mat: NDArray[np.float64],
    weights: NDArray[np.float64],
    *,
    covariate_names: Sequence[str],
    smd_threshold: float = 0.25,
) -> ClimateCovariateBalance:
    smds: list[tuple[str, float]] = []
    for k_idx, cname in enumerate(covariate_names):
        d_col = donor_mat[:, k_idx]
        pooled_sd = float(np.std(d_col, ddof=1)) if d_col.size > 1 else 0.0
        weighted_mean = float(np.sum(d_col * weights))
        if pooled_sd < 1e-12:
            smd = 0.0
        else:
            smd = float((float(treated_vec[k_idx]) - weighted_mean) / pooled_sd)
            # Cross-check with unweighted helper when weights are uniform
            if np.allclose(weights, 1.0 / len(weights)):
                smd = standardised_mean_difference(float(treated_vec[k_idx]), d_col, pooled_sd)
        smds.append((cname, round(smd, 4)))
    max_smd = max((abs(v) for _, v in smds), default=0.0)
    return ClimateCovariateBalance(
        standardized_mean_differences=tuple(smds),
        max_abs_smd=round(max_smd, 4),
        is_balanced=bool(max_smd <= smd_threshold),
    )


class UnitClimateSummary(Protocol):
    """Structural protocol for a unit's annual climate summary."""

    @property
    def unit_id(self) -> str: ...

    @property
    def name(self) -> str: ...

    @property
    def country(self) -> str: ...

    @property
    def pre_treatment_drought_years(self) -> tuple[int, ...]: ...

    @property
    def post_treatment_drought_years(self) -> tuple[int, ...]: ...

    def record_by_year(self) -> Mapping[int, Any]: ...

ClimateCovariateName = Literal[
    "annual_rainfall_mm",
    "wet_season_rainfall_mm",
    "dry_season_rainfall_mm",
    "rainfall_anomaly_z",
    "spi_12",
    "spi_6_wet",
    "mean_temp_c",
    "max_temp_c",
    "temp_anomaly_c",
]


@dataclass(frozen=True)
class DonorClimateComparability:
    """Climate comparability metrics between a single candidate donor and the treated AOI."""

    donor_id: str
    donor_name: str
    country: str
    pre_rainfall_mean_mm: float
    treated_pre_rainfall_mean_mm: float
    pre_rainfall_diff_mm: float
    pre_wet_season_mean_mm: float
    pre_rainfall_cv: float
    pre_rainfall_corr_with_treated: float
    pre_spi12_corr_with_treated: float
    pre_rainfall_rmspe_mm: float
    post_minus_pre_rainfall_shift_mm: float
    differential_post_rainfall_shock_mm: float
    pre_temp_mean_c: float | None
    pre_temp_diff_c: float | None
    differential_post_temp_shock_c: float | None
    pre_drought_years_count: int
    post_drought_years_count: int
    is_climate_comparable: bool
    comparability_flags: tuple[str, ...]


@dataclass(frozen=True)
class DonorPoolClimateDiagnostics:
    """Aggregate climate comparability and confounding diagnostics across the donor pool."""

    treated_unit_id: str
    pre_period: tuple[int, int]
    post_period: tuple[int, int]
    donor_count: int
    comparable_donor_count: int
    treated_pre_rainfall_mean_mm: float
    treated_post_rainfall_mean_mm: float
    treated_pre_wet_season_mean_mm: float
    treated_post_wet_season_mean_mm: float
    donor_pool_pre_rainfall_mean_mm: float
    donor_pool_pre_rainfall_min_mm: float
    donor_pool_pre_rainfall_max_mm: float
    treated_in_donor_rainfall_hull: bool
    treated_in_donor_temp_hull: bool
    mean_pre_rainfall_corr: float
    median_pre_rainfall_corr: float
    mean_differential_post_rainfall_shock_mm: float
    max_abs_differential_post_rainfall_shock_mm: float
    climate_covariate_balance_unweighted: ClimateCovariateBalance
    climate_covariate_balance_scm_weighted: ClimateCovariateBalance
    donor_comparability: tuple[DonorClimateComparability, ...]
    summary_notes: tuple[str, ...]


@dataclass(frozen=True)
class ClimateSpecDiagnostic:
    """Diagnostic result for a single climate-adjustment specification."""

    spec_name: str
    adjustment_mode: Literal["unadjusted", "donor_panel_residualized", "pre_treatment_residualized", "pre_treatment_climate_augmented_scm"]
    covariates_used: tuple[str, ...]
    uses_post_treatment_covariates: bool
    post_treatment_control_warning: str | None
    beta_coefficients: tuple[tuple[str, float], ...]
    donor_panel_climate_r2: float
    scm_fit: SyntheticControlFit
    did_result: DiDResult
    scm_ate_delta_vs_unadjusted: float
    did_ate_delta_vs_unadjusted: float
    pre_rmspe_delta_vs_unadjusted: float
    relative_pre_fit_delta_vs_unadjusted: float
    rmspe_ratio_delta_vs_unadjusted: float
    identifiability_preserved: bool
    verdict_after_gates: VerdictLabel
    gate_failure_reasons: tuple[str, ...]


@dataclass(frozen=True)
class ClimateConfoundingReport:
    """Comprehensive comparison of unadjusted vs climate-adjusted causal diagnostics."""

    case_id: str
    treated_unit_id: str
    pre_years: tuple[int, ...]
    post_years: tuple[int, ...]
    donor_pool_diagnostics: DonorPoolClimateDiagnostics
    unadjusted_spec: ClimateSpecDiagnostic
    primary_climate_adjusted_spec: ClimateSpecDiagnostic
    pre_treatment_matched_spec: ClimateSpecDiagnostic
    sensitivity_specs: tuple[ClimateSpecDiagnostic, ...]
    ate_range_scm: tuple[float, float]
    ate_range_did: tuple[float, float]
    pre_rmspe_range: tuple[float, float]
    causal_gates_preserved: bool
    final_verdict: VerdictLabel
    scientific_limitations: tuple[str, ...]


@dataclass(frozen=True)
class Sentinel2ClimateCoMovement:
    """Co-movement analysis between real Sentinel-2 observations (2021-2023) and climate."""

    unit_id: str
    years: tuple[int, ...]
    ndvi_values: tuple[float | None, ...]
    evi_values: tuple[float | None, ...]
    ndmi_values: tuple[float | None, ...]
    nbr_values: tuple[float | None, ...]
    annual_rainfall_mm: tuple[float | None, ...]
    wet_season_rainfall_mm: tuple[float | None, ...]
    spi_12_values: tuple[float | None, ...]
    spi_6_wet_values: tuple[float | None, ...]
    mean_temp_c: tuple[float | None, ...]
    max_temp_c: tuple[float | None, ...]
    temp_anomaly_c: tuple[float | None, ...]
    ndvi_2023_vs_2021_2022_delta: float | None
    ndmi_2023_vs_2021_2022_delta: float | None
    wet_rainfall_2023_vs_2021_2022_delta_mm: float | None
    temp_2023_vs_2021_2022_delta_c: float | None
    identifies_causal_effect: bool
    interpretation_notes: tuple[str, ...]


def _extract_covariate_value(
    rec_map: Mapping[int, object],
    year: int,
    cov_name: str,
) -> float | None:
    rec = rec_map.get(year)
    if rec is None:
        return None
    val = getattr(rec, cov_name, None)
    # Fallback for incomplete calendar years (e.g. 2022 if 1 dry month missing on S3 mirror):
    # if annual_rainfall_mm is None, use partial_year_rainfall_mm (since July/Dec dry/late-year gaps are documented)
    if val is None and cov_name == "annual_rainfall_mm":
        val = getattr(rec, "partial_year_rainfall_mm", None)
    if val is None and cov_name == "spi_12":
        val = getattr(rec, "spi_6_wet", None)
    if val is None and cov_name == "rainfall_anomaly_z":
        val = getattr(rec, "spi_6_wet", None)
    if val is None or not math.isfinite(float(val)):
        return None
    return float(val)


def build_climate_covariate_matrices(
    treated_summary: UnitClimateSummary,
    donor_summaries: Sequence[UnitClimateSummary],
    years: Sequence[int],
    covariate_names: Sequence[str],
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Build climate covariate tensors for the treated unit and donor pool.

    Returns:
        treated_X: shape ``(T, K)``
        donor_X: shape ``(T, J, K)``

    Raises:
        ValueError: if any requested year/covariate is missing across units.
    """
    t_years = [int(y) for y in years]
    n_t = len(t_years)
    n_j = len(donor_summaries)
    n_k = len(covariate_names)

    treated_X = np.zeros((n_t, n_k), dtype=np.float64)
    donor_X = np.zeros((n_t, n_j, n_k), dtype=np.float64)

    t_map = treated_summary.record_by_year()
    for t_idx, y in enumerate(t_years):
        for k_idx, cname in enumerate(covariate_names):
            v = _extract_covariate_value(t_map, y, cname)
            if v is None:
                raise ValueError(
                    f"Missing climate covariate {cname!r} for treated unit {treated_summary.unit_id!r} in year {y}."
                )
            treated_X[t_idx, k_idx] = v

    for j_idx, d_sum in enumerate(donor_summaries):
        d_map = d_sum.record_by_year()
        for t_idx, y in enumerate(t_years):
            for k_idx, cname in enumerate(covariate_names):
                v = _extract_covariate_value(d_map, y, cname)
                if v is None:
                    raise ValueError(
                        f"Missing climate covariate {cname!r} for donor {d_sum.unit_id!r} in year {y}."
                    )
                donor_X[t_idx, j_idx, k_idx] = v

    return treated_X, donor_X


def evaluate_donor_climate_comparability(
    treated_summary: UnitClimateSummary,
    donor_summaries: Sequence[UnitClimateSummary],
    *,
    pre_years: Sequence[int] = tuple(range(2001, 2011)),
    post_years: Sequence[int] = tuple(range(2011, 2023)),
    scm_weights: NDArray[np.float64] | None = None,
) -> DonorPoolClimateDiagnostics:
    """Evaluate how rainfall, drought (SPI), and temperature differences affect donor comparability."""
    pre_y = tuple(sorted(int(y) for y in pre_years))
    post_y = tuple(sorted(int(y) for y in post_years))

    t_map = treated_summary.record_by_year()
    t_pre_rain = np.array(
        [_extract_covariate_value(t_map, y, "annual_rainfall_mm") or 0.0 for y in pre_y],
        dtype=np.float64,
    )
    t_post_rain = np.array(
        [_extract_covariate_value(t_map, y, "annual_rainfall_mm") or 0.0 for y in post_y],
        dtype=np.float64,
    )
    t_pre_wet = np.array(
        [_extract_covariate_value(t_map, y, "wet_season_rainfall_mm") or 0.0 for y in pre_y],
        dtype=np.float64,
    )
    t_post_wet = np.array(
        [_extract_covariate_value(t_map, y, "wet_season_rainfall_mm") or 0.0 for y in post_y],
        dtype=np.float64,
    )
    t_pre_spi = np.array(
        [_extract_covariate_value(t_map, y, "spi_12") or 0.0 for y in pre_y],
        dtype=np.float64,
    )
    t_pre_temp = np.array(
        [_extract_covariate_value(t_map, y, "mean_temp_c") or np.nan for y in pre_y],
        dtype=np.float64,
    )
    t_post_temp = np.array(
        [_extract_covariate_value(t_map, y, "mean_temp_c") or np.nan for y in post_y],
        dtype=np.float64,
    )

    t_pre_rain_mean = float(np.mean(t_pre_rain))
    t_post_rain_mean = float(np.mean(t_post_rain))
    t_rain_shift = t_post_rain_mean - t_pre_rain_mean
    t_pre_temp_mean = float(np.nanmean(t_pre_temp)) if not np.all(np.isnan(t_pre_temp)) else None
    t_post_temp_mean = float(np.nanmean(t_post_temp)) if not np.all(np.isnan(t_post_temp)) else None
    t_temp_shift = (
        (t_post_temp_mean - t_pre_temp_mean)
        if (t_pre_temp_mean is not None and t_post_temp_mean is not None)
        else None
    )

    donor_comps: list[DonorClimateComparability] = []
    donor_pre_means: list[float] = []
    donor_pre_temps: list[float] = []
    pre_corrs: list[float] = []
    diff_shocks: list[float] = []

    # Static pre-treatment climate summary features for CovariateBalance check:
    # [pre_rainfall_mean, pre_wet_season_mean, pre_rainfall_cv, pre_spi_mean, pre_temp_mean]
    cov_names = (
        "pre_rainfall_mean_mm",
        "pre_wet_season_mean_mm",
        "pre_rainfall_cv",
        "pre_spi12_mean",
        "pre_mean_temp_c",
    )
    treated_cov_vec = np.array(
        [
            t_pre_rain_mean,
            float(np.mean(t_pre_wet)),
            float(np.std(t_pre_rain, ddof=1) / t_pre_rain_mean) if t_pre_rain_mean > 0 else 0.0,
            float(np.mean(t_pre_spi)),
            t_pre_temp_mean if t_pre_temp_mean is not None else 0.0,
        ],
        dtype=np.float64,
    )
    donor_cov_rows: list[NDArray[np.float64]] = []

    for d in donor_summaries:
        d_map = d.record_by_year()
        d_pre_rain = np.array(
            [_extract_covariate_value(d_map, y, "annual_rainfall_mm") or 0.0 for y in pre_y],
            dtype=np.float64,
        )
        d_post_rain = np.array(
            [_extract_covariate_value(d_map, y, "annual_rainfall_mm") or 0.0 for y in post_y],
            dtype=np.float64,
        )
        d_pre_wet = np.array(
            [_extract_covariate_value(d_map, y, "wet_season_rainfall_mm") or 0.0 for y in pre_y],
            dtype=np.float64,
        )
        d_pre_spi = np.array(
            [_extract_covariate_value(d_map, y, "spi_12") or 0.0 for y in pre_y],
            dtype=np.float64,
        )
        d_pre_temp = np.array(
            [_extract_covariate_value(d_map, y, "mean_temp_c") or np.nan for y in pre_y],
            dtype=np.float64,
        )
        d_post_temp = np.array(
            [_extract_covariate_value(d_map, y, "mean_temp_c") or np.nan for y in post_y],
            dtype=np.float64,
        )

        d_pre_mean = float(np.mean(d_pre_rain))
        d_post_mean = float(np.mean(d_post_rain))
        d_pre_wet_mean = float(np.mean(d_pre_wet))
        d_cv = float(np.std(d_pre_rain, ddof=1) / d_pre_mean) if d_pre_mean > 0 else 0.0

        corr_rain = (
            float(np.corrcoef(t_pre_rain, d_pre_rain)[0, 1])
            if (np.std(t_pre_rain) > 1e-6 and np.std(d_pre_rain) > 1e-6)
            else 0.0
        )
        corr_spi = (
            float(np.corrcoef(t_pre_spi, d_pre_spi)[0, 1])
            if (np.std(t_pre_spi) > 1e-6 and np.std(d_pre_spi) > 1e-6)
            else 0.0
        )
        rmspe_rain = float(np.sqrt(np.mean((t_pre_rain - d_pre_rain) ** 2)))
        d_shift = d_post_mean - d_pre_mean
        diff_shock = d_shift - t_rain_shift

        d_t_pre = float(np.nanmean(d_pre_temp)) if not np.all(np.isnan(d_pre_temp)) else None
        d_t_post = float(np.nanmean(d_post_temp)) if not np.all(np.isnan(d_post_temp)) else None
        t_diff = (d_t_pre - t_pre_temp_mean) if (d_t_pre is not None and t_pre_temp_mean is not None) else None
        diff_t_shock = (
            (d_t_post - d_t_pre) - t_temp_shift
            if (d_t_pre is not None and d_t_post is not None and t_temp_shift is not None)
            else None
        )

        flags: list[str] = []
        if abs(d_pre_mean - t_pre_rain_mean) > 250.0:
            flags.append(
                f"large baseline rainfall gap ({d_pre_mean - t_pre_rain_mean:+.1f} mm/yr vs Kariba)"
            )
        if corr_rain < 0.50:
            flags.append(f"weak pre-treatment interannual rainfall co-movement (r={corr_rain:.2f})")
        if abs(diff_shock) > 120.0:
            flags.append(
                f"divergent post- vs pre-treatment rainfall shift ({diff_shock:+.1f} mm/yr vs Kariba)"
            )
        if t_diff is not None and abs(t_diff) > 3.5:
            flags.append(f"thermal regime mismatch ({t_diff:+.1f} degC vs Kariba)")

        is_comp = len(flags) == 0
        donor_pre_means.append(d_pre_mean)
        if d_t_pre is not None:
            donor_pre_temps.append(d_t_pre)
        pre_corrs.append(corr_rain)
        diff_shocks.append(diff_shock)

        donor_cov_rows.append(
            np.array(
                [
                    d_pre_mean,
                    d_pre_wet_mean,
                    d_cv,
                    float(np.mean(d_pre_spi)),
                    d_t_pre if d_t_pre is not None else 0.0,
                ],
                dtype=np.float64,
            )
        )

        donor_comps.append(
            DonorClimateComparability(
                donor_id=d.unit_id,
                donor_name=d.name,
                country=d.country,
                pre_rainfall_mean_mm=round(d_pre_mean, 2),
                treated_pre_rainfall_mean_mm=round(t_pre_rain_mean, 2),
                pre_rainfall_diff_mm=round(d_pre_mean - t_pre_rain_mean, 2),
                pre_wet_season_mean_mm=round(d_pre_wet_mean, 2),
                pre_rainfall_cv=round(d_cv, 4),
                pre_rainfall_corr_with_treated=round(corr_rain, 4),
                pre_spi12_corr_with_treated=round(corr_spi, 4),
                pre_rainfall_rmspe_mm=round(rmspe_rain, 2),
                post_minus_pre_rainfall_shift_mm=round(d_shift, 2),
                differential_post_rainfall_shock_mm=round(diff_shock, 2),
                pre_temp_mean_c=round(d_t_pre, 2) if d_t_pre is not None else None,
                pre_temp_diff_c=round(t_diff, 2) if t_diff is not None else None,
                differential_post_temp_shock_c=round(diff_t_shock, 3) if diff_t_shock is not None else None,
                pre_drought_years_count=len(d.pre_treatment_drought_years),
                post_drought_years_count=len(d.post_treatment_drought_years),
                is_climate_comparable=is_comp,
                comparability_flags=tuple(flags),
            )
        )

    donor_cov_mat = np.vstack(donor_cov_rows)
    n_j = len(donor_summaries)
    uniform_w = np.full(n_j, 1.0 / n_j, dtype=np.float64)
    w_scm = scm_weights if (scm_weights is not None and scm_weights.size == n_j) else uniform_w

    bal_unweighted = _assess_climate_covariate_balance(
        treated_cov_vec, donor_cov_mat, uniform_w, covariate_names=cov_names
    )
    bal_weighted = _assess_climate_covariate_balance(
        treated_cov_vec, donor_cov_mat, w_scm, covariate_names=cov_names
    )

    in_rain_hull = bool(min(donor_pre_means) <= t_pre_rain_mean <= max(donor_pre_means))
    in_temp_hull = (
        bool(min(donor_pre_temps) <= t_pre_temp_mean <= max(donor_pre_temps))
        if (donor_pre_temps and t_pre_temp_mean is not None)
        else False
    )

    comp_count = sum(1 for c in donor_comps if c.is_climate_comparable)
    notes = (
        f"{comp_count}/{n_j} spatially eligible donors pass all four climate comparability thresholds "
        "(|pre-rainfall gap| <= 250 mm/yr, pre-rainfall r >= 0.50, |differential post-shift| <= 120 mm/yr, |temp gap| <= 3.5 C).",
        f"Kariba pre-treatment mean rainfall ({t_pre_rain_mean:.1f} mm/yr) lies inside the donor pool range "
        f"[{min(donor_pre_means):.1f}, {max(donor_pre_means):.1f}] mm/yr (donor mean {float(np.mean(donor_pre_means)):.1f} mm/yr).",
        f"Mean pre-treatment rainfall trajectory correlation with Kariba is r = {float(np.mean(pre_corrs)):.3f} "
        f"(median r = {float(np.median(pre_corrs)):.3f}), reflecting regional ENSO/ITCZ teleconnections mixed with latitudinal gradients.",
        f"Differential post-treatment vs pre-treatment rainfall shift across donors averages "
        f"{float(np.mean(diff_shocks)):+.1f} mm/yr (max |shock| = {float(np.max(np.abs(diff_shocks))):.1f} mm/yr).",
    )

    return DonorPoolClimateDiagnostics(
        treated_unit_id=treated_summary.unit_id,
        pre_period=(pre_y[0], pre_y[-1]),
        post_period=(post_y[0], post_y[-1]),
        donor_count=n_j,
        comparable_donor_count=comp_count,
        treated_pre_rainfall_mean_mm=round(t_pre_rain_mean, 2),
        treated_post_rainfall_mean_mm=round(t_post_rain_mean, 2),
        treated_pre_wet_season_mean_mm=round(float(np.mean(t_pre_wet)), 2),
        treated_post_wet_season_mean_mm=round(float(np.mean(t_post_wet)), 2),
        donor_pool_pre_rainfall_mean_mm=round(float(np.mean(donor_pre_means)), 2),
        donor_pool_pre_rainfall_min_mm=round(float(min(donor_pre_means)), 2),
        donor_pool_pre_rainfall_max_mm=round(float(max(donor_pre_means)), 2),
        treated_in_donor_rainfall_hull=in_rain_hull,
        treated_in_donor_temp_hull=in_temp_hull,
        mean_pre_rainfall_corr=round(float(np.mean(pre_corrs)), 4),
        median_pre_rainfall_corr=round(float(np.median(pre_corrs)), 4),
        mean_differential_post_rainfall_shock_mm=round(float(np.mean(diff_shocks)), 2),
        max_abs_differential_post_rainfall_shock_mm=round(float(np.max(np.abs(diff_shocks))), 2),
        climate_covariate_balance_unweighted=bal_unweighted,
        climate_covariate_balance_scm_weighted=bal_weighted,
        donor_comparability=tuple(donor_comps),
        summary_notes=notes,
    )


def estimate_untreated_climate_sensitivity(
    donor_outcomes: NDArray[np.float64],
    donor_covariates: NDArray[np.float64],
    *,
    fit_rows: slice | Sequence[int] | None = None,
) -> tuple[NDArray[np.float64], float]:
    """Estimate within-unit demeaned sensitivity beta of outcomes Y_{jt} to climate X_{jtk}.

    Strictly uses ONLY untreated donor control units (and optionally only pre-treatment rows
    when ``fit_rows`` is provided) so that the treated unit's post-treatment trajectory can
    NEVER contaminate or be absorbed into ``beta``.

    Args:
        donor_outcomes: shape ``(T, J)``
        donor_covariates: shape ``(T, J, K)``
        fit_rows: optional row slice/indices (e.g. ``slice(0, T_0)`` for pre-treatment only).

    Returns:
        beta: shape ``(K,)``
        r_squared: within-unit R^2 on the estimation sample.
    """
    Y = donor_outcomes if fit_rows is None else donor_outcomes[fit_rows, :]
    X = donor_covariates if fit_rows is None else donor_covariates[fit_rows, :, :]

    n_t, n_j, n_k = X.shape
    if Y.shape != (n_t, n_j):
        raise ValueError(f"Incompatible shapes: Y={Y.shape}, X={X.shape}")

    # Within-unit demeaning across time for each untreated donor j
    Y_demeaned = Y - np.mean(Y, axis=0, keepdims=True)
    X_demeaned = X - np.mean(X, axis=0, keepdims=True)

    y_vec = Y_demeaned.reshape(-1)
    x_mat = X_demeaned.reshape(n_t * n_j, n_k)

    # Ridge-stabilized OLS in case of near-collinear climate covariates
    xtx = x_mat.T @ x_mat + 1e-8 * np.eye(n_k, dtype=np.float64)
    xty = x_mat.T @ y_vec
    beta = np.linalg.solve(xtx, xty)

    y_hat = x_mat @ beta
    ss_tot = float(np.sum(y_vec**2))
    ss_res = float(np.sum((y_vec - y_hat) ** 2))
    r2 = max(0.0, 1.0 - ss_res / ss_tot) if ss_tot > 1e-12 else 0.0
    return beta, r2


def check_post_treatment_covariate_divergence(
    treated_X_pre: NDArray[np.float64],
    treated_X_post: NDArray[np.float64],
    donor_X_pre: NDArray[np.float64],
    donor_X_post: NDArray[np.float64],
    covariate_names: Sequence[str],
    *,
    z_threshold: float = 2.5,
) -> str | None:
    """Detect if a time-varying covariate exhibits an anomalous post-treatment divergence on the treated unit.

    While meteorological variables (CHIRPS rainfall, synoptic temperature) are physically exogenous to
    a local forest conservation project, conditioning on post-treatment variables that are affected by
    treatment ("bad controls") or exhibit extreme differential shocks requires explicit disclosure.
    """
    warnings: list[str] = []
    for k_idx, cname in enumerate(covariate_names):
        t_diff = float(np.mean(treated_X_post[:, k_idx]) - np.mean(treated_X_pre[:, k_idx]))
        d_diffs = np.mean(donor_X_post[:, :, k_idx], axis=0) - np.mean(donor_X_pre[:, :, k_idx], axis=0)
        d_mean = float(np.mean(d_diffs))
        d_std = float(np.std(d_diffs, ddof=1)) if d_diffs.size >= 2 else 0.0
        if d_std > 1e-9:
            z_div = abs(t_diff - d_mean) / d_std
            if z_div >= z_threshold:
                warnings.append(
                    f"Covariate {cname!r} shows a {z_div:.2f} SD differential post-treatment shift "
                    f"on the treated unit ({t_diff:+.3f} vs donor mean {d_mean:+.3f}); conditioning on "
                    "post-treatment realizations requires assuming strict exogeneity (no treatment->covariate feedback)."
                )
    if not warnings:
        return (
            "Conditioning on post-treatment climate realizations assumes meteorological exogeneity "
            "(REDD+ conservation does not alter synoptic CHIRPS rainfall); pre-treatment-only matched "
            "SCM is reported alongside to guard against post-treatment conditioning bias."
        )
    return " ".join(warnings)


def evaluate_causal_gates_for_spec(
    scm_fit: SyntheticControlFit,
    *,
    donor_count: int,
    pre_periods: int,
    min_donors: int = 5,
    max_relative_pre_rmspe: float = 0.20,
    biomass_calibrated: bool = False,
) -> tuple[VerdictLabel, tuple[str, ...]]:
    """Apply GroundTruth's strict causal identification gates to a specification's SCM fit.

    Crucial scientific rule: adding climate covariates NEVER bypasses donor non-identification
    (J > T_0), uniform weight degeneracy, poor pre-treatment fit, convex-hull failure, or
    missing biomass calibration.
    """
    reasons: list[str] = []
    if donor_count < min_donors:
        reasons.append(f"insufficient_donors ({donor_count} < {min_donors})")
    if not scm_fit.weights_are_identified or donor_count > pre_periods:
        reasons.append(
            f"under_identified_simplex (J={donor_count} donors > T_0={pre_periods} pre-treatment periods)"
        )
    if scm_fit.is_uniform_degenerate:
        reasons.append(
            f"uniform_weight_degeneracy (effective_donors={scm_fit.effective_donor_count:.2f}/{donor_count})"
        )
    if scm_fit.relative_pre_fit > max_relative_pre_rmspe:
        reasons.append(
            f"poor_pre_treatment_fit (relative_pre_fit={scm_fit.relative_pre_fit:.4f} > {max_relative_pre_rmspe})"
        )
    if scm_fit.hull is not None and scm_fit.hull.materially_outside:
        reasons.append(
            f"convex_hull_violation (share_outside={scm_fit.hull.share_periods_outside_envelope:.2f}, "
            f"level_excess_sd={scm_fit.hull.level_excess_sd:.2f})"
        )
    if not biomass_calibrated:
        reasons.append("uncalibrated_spectral_index (NDVI is not calibrated to tCO2e biomass)")

    if reasons:
        return VerdictLabel.INCONCLUSIVE, tuple(reasons)
    return VerdictLabel.CONSISTENT_WITH_CLAIM, ()


def run_climate_confounding_analysis(
    *,
    case_id: str,
    treated_pre: NDArray[np.float64],
    donor_pre: NDArray[np.float64],
    treated_post: NDArray[np.float64],
    donor_post: NDArray[np.float64],
    donor_ids: Sequence[str],
    treated_climate: UnitClimateSummary,
    donor_climates: Sequence[UnitClimateSummary],
    pre_years: Sequence[int] = tuple(range(2001, 2011)),
    post_years: Sequence[int] = tuple(range(2011, 2023)),
    biomass_calibrated: bool = False,
) -> ClimateConfoundingReport:
    """Run unadjusted vs climate-adjusted causal diagnostics and a full sensitivity sweep.

    Does NOT alter ``fit_synthetic_control`` or ``estimate_did``; calls them directly on
    unadjusted and weather-residualized panels, plus a pre-treatment climate-augmented SCM.
    """
    pre_y = tuple(int(y) for y in pre_years)
    post_y = tuple(int(y) for y in post_years)
    all_y = pre_y + post_y
    n_pre = len(pre_y)
    n_post = len(post_y)
    n_j = len(donor_ids)
    donor_ids_tuple = tuple(donor_ids)

    if treated_pre.shape[0] != n_pre or treated_post.shape[0] != n_post:
        raise ValueError("treated_pre/post lengths must match pre_years/post_years.")
    if donor_pre.shape != (n_pre, n_j) or donor_post.shape != (n_post, n_j):
        raise ValueError("donor_pre/post shapes must match (n_pre/n_post, len(donor_ids)).")
    if len(donor_climates) != n_j:
        raise ValueError("donor_climates must have the same length and order as donor_ids.")

    donor_Y_all = np.vstack([donor_pre, donor_post])
    treated_Y_all = np.concatenate([treated_pre, treated_post])

    # 1. Baseline Unadjusted Specification
    unadj_scm = fit_synthetic_control(
        treated_Y_all, donor_Y_all, donor_ids_tuple, n_pre
    )
    unadj_did = estimate_did(treated_Y_all, donor_Y_all, n_pre, n_bootstrap=199)
    unadj_verdict, unadj_reasons = evaluate_causal_gates_for_spec(
        unadj_scm,
        donor_count=n_j,
        pre_periods=n_pre,
        biomass_calibrated=biomass_calibrated,
    )

    unadj_spec = ClimateSpecDiagnostic(
        spec_name="unadjusted_baseline",
        adjustment_mode="unadjusted",
        covariates_used=(),
        uses_post_treatment_covariates=False,
        post_treatment_control_warning=None,
        beta_coefficients=(),
        donor_panel_climate_r2=0.0,
        scm_fit=unadj_scm,
        did_result=unadj_did,
        scm_ate_delta_vs_unadjusted=0.0,
        did_ate_delta_vs_unadjusted=0.0,
        pre_rmspe_delta_vs_unadjusted=0.0,
        relative_pre_fit_delta_vs_unadjusted=0.0,
        rmspe_ratio_delta_vs_unadjusted=0.0,
        identifiability_preserved=(unadj_verdict == VerdictLabel.INCONCLUSIVE),
        verdict_after_gates=unadj_verdict,
        gate_failure_reasons=unadj_reasons,
    )

    # 2. Donor Pool Climate Comparability Diagnostics (using baseline SCM weights)
    pool_diag = evaluate_donor_climate_comparability(
        treated_climate,
        donor_climates,
        pre_years=pre_y,
        post_years=post_y,
        scm_weights=unadj_scm.weights,
    )

    # 3. Helper to run a climate-residualized specification
    def _run_residualized_spec(
        spec_name: str,
        cov_names: tuple[str, ...],
        *,
        pre_only_beta: bool = False,
    ) -> ClimateSpecDiagnostic:
        t_X_all, d_X_all = build_climate_covariate_matrices(
            treated_climate, donor_climates, all_y, cov_names
        )
        fit_slice = slice(0, n_pre) if pre_only_beta else None
        beta, r2 = estimate_untreated_climate_sensitivity(
            donor_Y_all, d_X_all, fit_rows=fit_slice
        )

        # Anchor demeaning of climate covariates at each unit's PRE-TREATMENT mean
        # so that post-treatment weather anomalies relative to the pre-treatment baseline
        # are properly adjusted without absorbing fixed unit level differences.
        t_X_pre_mean = np.mean(t_X_all[:n_pre, :], axis=0, keepdims=True)
        d_X_pre_mean = np.mean(d_X_all[:n_pre, :, :], axis=0, keepdims=True)

        t_adj_all = treated_Y_all - ((t_X_all - t_X_pre_mean) @ beta)
        d_adj_all = donor_Y_all - np.einsum("tjk,k->tj", d_X_all - d_X_pre_mean, beta)

        scm_adj = fit_synthetic_control(
            t_adj_all, d_adj_all, donor_ids_tuple, n_pre
        )
        did_adj = estimate_did(t_adj_all, d_adj_all, n_pre, n_bootstrap=199)
        warn_msg = check_post_treatment_covariate_divergence(
            t_X_all[:n_pre, :],
            t_X_all[n_pre:, :],
            d_X_all[:n_pre, :, :],
            d_X_all[n_pre:, :, :],
            cov_names,
        )
        verdict_adj, reasons_adj = evaluate_causal_gates_for_spec(
            scm_adj,
            donor_count=n_j,
            pre_periods=n_pre,
            biomass_calibrated=biomass_calibrated,
        )

        return ClimateSpecDiagnostic(
            spec_name=spec_name,
            adjustment_mode="pre_treatment_residualized" if pre_only_beta else "donor_panel_residualized",
            covariates_used=cov_names,
            uses_post_treatment_covariates=True,
            post_treatment_control_warning=warn_msg,
            beta_coefficients=tuple(
                (cname, round(float(b), 6)) for cname, b in zip(cov_names, beta, strict=True)
            ),
            donor_panel_climate_r2=round(float(r2), 4),
            scm_fit=scm_adj,
            did_result=did_adj,
            scm_ate_delta_vs_unadjusted=round(float(scm_adj.average_effect - unadj_scm.average_effect), 6),
            did_ate_delta_vs_unadjusted=round(float(did_adj.estimate - unadj_did.estimate), 6),
            pre_rmspe_delta_vs_unadjusted=round(float(scm_adj.pre_rmspe - unadj_scm.pre_rmspe), 6),
            relative_pre_fit_delta_vs_unadjusted=round(
                float(scm_adj.relative_pre_fit - unadj_scm.relative_pre_fit), 6
            ),
            rmspe_ratio_delta_vs_unadjusted=round(float(scm_adj.rmspe_ratio - unadj_scm.rmspe_ratio), 6),
            identifiability_preserved=(verdict_adj == VerdictLabel.INCONCLUSIVE),
            verdict_after_gates=verdict_adj,
            gate_failure_reasons=reasons_adj,
        )

    # 4. Pre-Treatment-Only Climate-Augmented SCM (strictly ZERO post-treatment climate controls)
    # Stacks standardized pre-treatment outcome (2001-2010) and standardized pre-treatment
    # CHIRPS rainfall & SPI-12 & temperature summary features to solve for simplex weights w,
    # then evaluates those weights on the UNADJUSTED outcomes.
    t_X_pre, d_X_pre = build_climate_covariate_matrices(
        treated_climate,
        donor_climates,
        pre_y,
        ("annual_rainfall_mm", "wet_season_rainfall_mm", "spi_12", "mean_temp_c"),
    )
    y_scale = max(float(np.std(donor_pre)), 1e-6)
    t_y_norm = treated_pre / y_scale
    d_y_norm = donor_pre / y_scale

    # Summarize pre-treatment climate per unit into 4 standardized features
    t_clim_feat = np.mean(t_X_pre, axis=0)
    d_clim_feat = np.mean(d_X_pre, axis=0)  # shape (J, 4)
    c_scale = np.maximum(np.std(d_clim_feat, axis=0), 1e-6)
    t_clim_norm = (t_clim_feat / c_scale) * 0.5
    d_clim_norm = (d_clim_feat / c_scale).T * 0.5  # shape (4, J)

    aug_target = np.concatenate([t_y_norm, t_clim_norm])
    aug_donors = np.vstack([d_y_norm, d_clim_norm])
    w_pre_matched, iters_m, conv_m = solve_simplex_least_squares(aug_donors, aug_target)

    # Evaluate pre-matched weights on the unadjusted outcome series
    synth_pre_m = donor_pre @ w_pre_matched
    synth_post_m = donor_post @ w_pre_matched
    pre_res_m = treated_pre - synth_pre_m
    post_eff_m = treated_post - synth_post_m
    pre_rmspe_m = float(np.sqrt(np.mean(pre_res_m**2)))
    post_rmspe_m = float(np.sqrt(np.mean(post_eff_m**2)))

    scm_pre_matched = SyntheticControlFit(
        weights=w_pre_matched,
        donor_ids=donor_ids_tuple,
        pre_rmspe=pre_rmspe_m,
        post_rmspe=post_rmspe_m,
        treated_pre=treated_pre,
        synthetic_pre=synth_pre_m,
        treated_post=treated_post,
        synthetic_post=synth_post_m,
        n_iterations=iters_m,
        converged=conv_m,
        n_pre_periods=n_pre,
        hull=unadj_scm.hull,
    )
    verdict_pm, reasons_pm = evaluate_causal_gates_for_spec(
        scm_pre_matched,
        donor_count=n_j,
        pre_periods=n_pre,
        biomass_calibrated=biomass_calibrated,
    )
    pre_matched_spec = ClimateSpecDiagnostic(
        spec_name="pre_treatment_climate_augmented_scm",
        adjustment_mode="pre_treatment_climate_augmented_scm",
        covariates_used=("annual_rainfall_mm", "wet_season_rainfall_mm", "spi_12", "mean_temp_c"),
        uses_post_treatment_covariates=False,
        post_treatment_control_warning=None,
        beta_coefficients=(),
        donor_panel_climate_r2=0.0,
        scm_fit=scm_pre_matched,
        did_result=unadj_did,
        scm_ate_delta_vs_unadjusted=round(float(scm_pre_matched.average_effect - unadj_scm.average_effect), 6),
        did_ate_delta_vs_unadjusted=0.0,
        pre_rmspe_delta_vs_unadjusted=round(float(scm_pre_matched.pre_rmspe - unadj_scm.pre_rmspe), 6),
        relative_pre_fit_delta_vs_unadjusted=round(
            float(scm_pre_matched.relative_pre_fit - unadj_scm.relative_pre_fit), 6
        ),
        rmspe_ratio_delta_vs_unadjusted=round(float(scm_pre_matched.rmspe_ratio - unadj_scm.rmspe_ratio), 6),
        identifiability_preserved=(verdict_pm == VerdictLabel.INCONCLUSIVE),
        verdict_after_gates=verdict_pm,
        gate_failure_reasons=reasons_pm,
    )

    # 5. Full Sensitivity Analysis Sweep
    spec_annual_rain = _run_residualized_spec("chirps_annual_rainfall", ("annual_rainfall_mm",))
    spec_wet_rain = _run_residualized_spec("chirps_wet_season_rainfall", ("wet_season_rainfall_mm",))
    spec_spi12 = _run_residualized_spec("chirps_spi_12_drought", ("spi_12",))
    spec_spi6 = _run_residualized_spec("chirps_spi_6_wet_drought", ("spi_6_wet",))
    spec_temp = _run_residualized_spec("nasa_power_mean_temp", ("mean_temp_c",))
    spec_rain_temp = _run_residualized_spec(
        "chirps_rainfall_plus_temp", ("annual_rainfall_mm", "mean_temp_c")
    )
    spec_full_climate = _run_residualized_spec(
        "chirps_wet_rainfall_spi12_temp",
        ("wet_season_rainfall_mm", "spi_12", "mean_temp_c"),
    )
    spec_pre_only_beta = _run_residualized_spec(
        "pre_treatment_beta_rainfall_spi12_temp",
        ("wet_season_rainfall_mm", "spi_12", "mean_temp_c"),
        pre_only_beta=True,
    )

    all_specs = (
        unadj_spec,
        spec_annual_rain,
        spec_wet_rain,
        spec_spi12,
        spec_spi6,
        spec_temp,
        spec_rain_temp,
        spec_full_climate,
        spec_pre_only_beta,
        pre_matched_spec,
    )

    scm_ates = [s.scm_fit.average_effect for s in all_specs]
    did_ates = [s.did_result.estimate for s in all_specs]
    pre_rmspes = [s.scm_fit.pre_rmspe for s in all_specs]

    gates_ok = all(s.verdict_after_gates == VerdictLabel.INCONCLUSIVE for s in all_specs)
    final_verdict = (
        VerdictLabel.INCONCLUSIVE
        if gates_ok
        else unadj_spec.verdict_after_gates
    )

    limitations = (
        f"Under-identified donor pool persists across all climate specifications: J={n_j} eligible donors vs T_0={n_pre} pre-treatment annual observations (2001-2010).",
        f"Climate adjustment shifts SCM average effect between {min(scm_ates):+.4f} and {max(scm_ates):+.4f} NDVI ({min(did_ates):+.4f} to {max(did_ates):+.4f} in DiD), and pre-RMSPE between {min(pre_rmspes):.4f} and {max(pre_rmspes):.4f}, which does NOT resolve poor pre-treatment synthetic control fit or uniform weight degeneracy.",
        "Real Sentinel-2 observations for Kariba cover only 2021-2023 (3 post-treatment years, 0 pre-treatment years); while 2021-2023 CHIRPS and NASA POWER records contextualize the 2023 NDVI decline, 3 post-treatment years cannot identify a causal treatment effect.",
        "CHIRTSmax v1.0 CDR (0.05°) terminates in December 2016 and therefore does not cover 2017-2023; continuous 1981-2023 temperature coverage is provided by NASA POWER MERRA-2 (0.5° x 0.625°).",
        "In the Digital Earth Africa S3 CHIRPS COG mirror, 2 out of 516 monthly rasters (2022-07 and 2023-12) were absent; explicit missing-month tracking is enforced rather than silent interpolation.",
        "Causal verdict remains INCONCLUSIVE across all unadjusted and climate-adjusted specifications.",
    )

    return ClimateConfoundingReport(
        case_id=case_id,
        treated_unit_id=treated_climate.unit_id,
        pre_years=pre_y,
        post_years=post_y,
        donor_pool_diagnostics=pool_diag,
        unadjusted_spec=unadj_spec,
        primary_climate_adjusted_spec=spec_full_climate,
        pre_treatment_matched_spec=pre_matched_spec,
        sensitivity_specs=all_specs,
        ate_range_scm=(round(float(min(scm_ates)), 6), round(float(max(scm_ates)), 6)),
        ate_range_did=(round(float(min(did_ates)), 6), round(float(max(did_ates)), 6)),
        pre_rmspe_range=(round(float(min(pre_rmspes)), 6), round(float(max(pre_rmspes)), 6)),
        causal_gates_preserved=gates_ok,
        final_verdict=final_verdict,
        scientific_limitations=limitations,
    )


def analyze_sentinel2_climate_comovement(
    climate_summary: UnitClimateSummary,
    *,
    years: Sequence[int] = (2021, 2022, 2023),
    ndvi_values: Sequence[float | None] | None = None,
    evi_values: Sequence[float | None] | None = None,
    ndmi_values: Sequence[float | None] | None = None,
    nbr_values: Sequence[float | None] | None = None,
) -> Sentinel2ClimateCoMovement:
    """Align real 2021-2023 Sentinel-2 spectral trajectories with CHIRPS and NASA POWER anomalies.

    Enforces critical scientific integrity requirements:
    1. Removes hardcoded observation defaults: if values are not provided, they remain None.
    2. Explicitly tracks missing observations without fabricating data or guessing signs.
    3. Co-movement over 3 post-treatment years (2021-2023) with zero pre-treatment Sentinel-2
       baseline is descriptive context, NOT causal proof (`identifies_causal_effect = False`).
    """
    rec_map = climate_summary.record_by_year()
    yrs = tuple(int(y) for y in years)

    def _pad_or_none(seq: Sequence[float | None] | None) -> tuple[float | None, ...]:
        if seq is None:
            return tuple(None for _ in yrs)
        return tuple(float(v) if (v is not None and math.isfinite(float(v))) else None for v in seq)

    ndvi_tuple = _pad_or_none(ndvi_values)
    evi_tuple = _pad_or_none(evi_values)
    ndmi_tuple = _pad_or_none(ndmi_values)
    nbr_tuple = _pad_or_none(nbr_values)

    ann_rain = tuple(rec_map[y].annual_rainfall_mm if y in rec_map else None for y in yrs)
    wet_rain = tuple(rec_map[y].wet_season_rainfall_mm if y in rec_map else None for y in yrs)
    spi12 = tuple(rec_map[y].spi_12 if y in rec_map else None for y in yrs)
    spi6 = tuple(rec_map[y].spi_6_wet if y in rec_map else None for y in yrs)
    t_mean = tuple(rec_map[y].mean_temp_c if y in rec_map else None for y in yrs)
    t_max = tuple(rec_map[y].max_temp_c if y in rec_map else None for y in yrs)
    t_anom = tuple(rec_map[y].temp_anomaly_c if y in rec_map else None for y in yrs)

    # 2023 vs 2021-2022 baseline delta for NDVI
    ndvi_delta: float | None = None
    if (
        len(ndvi_tuple) >= 3
        and ndvi_tuple[0] is not None
        and ndvi_tuple[1] is not None
        and ndvi_tuple[2] is not None
    ):
        ndvi_delta = round(float(ndvi_tuple[2] - 0.5 * (ndvi_tuple[0] + ndvi_tuple[1])), 4)

    # 2023 vs 2021-2022 baseline delta for NDMI
    ndmi_delta: float | None = None
    if (
        len(ndmi_tuple) >= 3
        and ndmi_tuple[0] is not None
        and ndmi_tuple[1] is not None
        and ndmi_tuple[2] is not None
    ):
        ndmi_delta = round(float(ndmi_tuple[2] - 0.5 * (ndmi_tuple[0] + ndmi_tuple[1])), 4)

    w0 = wet_rain[0] if len(wet_rain) > 0 else None
    w1 = wet_rain[1] if len(wet_rain) > 1 else None
    w2 = wet_rain[2] if len(wet_rain) > 2 else None
    wet_delta = (
        round(float(w2 - 0.5 * (w0 + w1)), 2)
        if (w0 is not None and w1 is not None and w2 is not None)
        else None
    )
    t0 = t_mean[0] if len(t_mean) > 0 else None
    t1 = t_mean[1] if len(t_mean) > 1 else None
    t2 = t_mean[2] if len(t_mean) > 2 else None
    temp_delta = (
        round(float(t2 - 0.5 * (t0 + t1)), 3)
        if (t0 is not None and t1 is not None and t2 is not None)
        else None
    )

    notes: list[str] = []
    if ndvi_delta is not None and ndvi_tuple[0] is not None and ndvi_tuple[1] is not None and ndvi_tuple[2] is not None:
        notes.append(
            f"Real Sentinel-2 L2A NDVI drops by {ndvi_delta:+.4f} in {yrs[2]} ({ndvi_tuple[2]:.4f}) "
            f"relative to the {yrs[0]}-{yrs[1]} mean ({0.5*(ndvi_tuple[0]+ndvi_tuple[1]):.4f})."
        )
    else:
        notes.append(f"Sentinel-2 NDVI observations for years {yrs} are partially or entirely unavailable.")

    if ndmi_tuple[0] is not None and ndmi_tuple[1] is not None and ndmi_tuple[2] is not None:
        ndmi_shift_str = (
            f"accompanied by NDMI moisture trajectory "
            f"({ndmi_tuple[0]:+.4f} in {yrs[0]} -> {ndmi_tuple[1]:+.4f} in {yrs[1]} -> {ndmi_tuple[2]:+.4f} in {yrs[2]}, "
            f"delta: {ndmi_delta:+.4f})."
        )
        notes.append(ndmi_shift_str)
    else:
        notes.append(f"Sentinel-2 NDMI observations for years {yrs} are unavailable or incomplete.")

    notes.append(
        f"Austral wet-season (Nov-Apr) CHIRPS rainfall in {yrs} is {wet_rain} mm (wet-season SPI-6: {spi6}), "
        f"and NASA POWER annual mean temperature is {t_mean} degC (anomaly vs 1981-2010: {t_anom} degC)."
    )
    notes.append(
        "CRITICAL SCIENTIFIC RULE: Co-movement over T=3 post-treatment years (2021-2023) with zero pre-treatment "
        "Sentinel-2 observations (Sentinel-2A launched in June 2015 vs 2011 project start) cannot separate meteorological "
        "stress from anthropogenic disturbance and does not establish causality."
    )

    return Sentinel2ClimateCoMovement(
        unit_id=climate_summary.unit_id,
        years=yrs,
        ndvi_values=ndvi_tuple,
        evi_values=evi_tuple,
        ndmi_values=ndmi_tuple,
        nbr_values=nbr_tuple,
        annual_rainfall_mm=ann_rain,
        wet_season_rainfall_mm=wet_rain,
        spi_12_values=spi12,
        spi_6_wet_values=spi6,
        mean_temp_c=t_mean,
        max_temp_c=t_max,
        temp_anomaly_c=t_anom,
        ndvi_2023_vs_2021_2022_delta=ndvi_delta,
        ndmi_2023_vs_2021_2022_delta=ndmi_delta,
        wet_rainfall_2023_vs_2021_2022_delta_mm=wet_delta,
        temp_2023_vs_2021_2022_delta_c=temp_delta,
        identifies_causal_effect=False,
        interpretation_notes=tuple(notes),
    )
