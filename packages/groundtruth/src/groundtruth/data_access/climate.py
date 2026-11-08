"""Climate data access, temporal aggregation, SPI drought calculation, and alignment.

Implements Task 3 items 1–8:
1. Integrates CHIRPS v2.0 0.05° precipitation data for the Kariba AOI and 37 eligible donor districts.
2. Covers complete historical climatology (1981–2000), pre-treatment (2001–2010), and post-treatment (2011–2023) periods.
3. Integrates NASA POWER MERRA-2 temperature indicators (T2M, T2M_MAX, T2M_MIN) and documents CHIRTSmax CDR (1983–2016) coverage horizon.
4. Computes annual and Austral seasonal (Nov–Apr wet season, May–Oct dry season) rainfall totals, anomalies, and variability (SD, CV, z-scores).
5. Computes Standardized Precipitation Index (SPI-12, SPI-6 wet season, SPI-3 peak wet season) via two-parameter Gamma fitting calibrated on the pre-treatment baseline (1981–2010).
6. Preserves source, resolution, temporal coverage, retrieval date, units, and processing provenance.
7. Aligns climate observations with satellite observation windows (2001–2022 panel window and 2021–2023 Sentinel-2 STAC window).
8. Handles missing periods, mirror gaps, and inconsistent temporal coverage explicitly without silent interpolation.
"""

from __future__ import annotations

import json
import math
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from groundtruth.contracts.errors import DataUnavailableError, InsufficientDataError
from groundtruth.contracts.units import convert_climate_unit, unit_family

DEFAULT_CLIMATE_CACHE_PATH = (
    Path(__file__).resolve().parents[5]
    / "data"
    / "processed"
    / "climate_cache"
    / "kariba_chirps_climate.json"
)


@dataclass(frozen=True)
class ClimateSourceProvenance:
    """Complete provenance record for an ingested climate dataset."""

    dataset_id: str
    provider: str
    source_uri: str
    resolution_deg: float
    resolution_km: float
    crs: str
    native_unit: str
    canonical_unit: str
    temporal_coverage_start: str
    temporal_coverage_end: str
    retrieved_at: str
    citation: str
    processing_steps: tuple[str, ...]
    known_coverage_gaps: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # Validate declared units against the contract vocabulary
        unit_family(self.native_unit)
        unit_family(self.canonical_unit)


@dataclass(frozen=True)
class AnnualClimateRecord:
    """Annual and seasonal climate metrics for a single spatial unit and year."""

    unit_id: str
    year: int
    valid_months: int
    missing_months: tuple[int, ...]
    is_complete_year: bool
    annual_rainfall_mm: float | None
    partial_year_rainfall_mm: float | None
    wet_season_rainfall_mm: float | None
    calendar_wet_months_mm: float | None
    dry_season_rainfall_mm: float | None
    rainfall_anomaly_mm: float | None
    rainfall_anomaly_pct: float | None
    rainfall_anomaly_z: float | None
    intra_annual_monthly_std_mm: float | None
    intra_annual_cv: float | None
    spi_12: float | None
    spi_6_wet: float | None
    spi_3_peak: float | None
    drought_classification: str
    mean_temp_c: float | None
    max_temp_c: float | None
    min_temp_c: float | None
    temp_anomaly_c: float | None
    temp_anomaly_z: float | None
    chirts_tmax_available: bool = False


@dataclass(frozen=True)
class UnitClimateSummary:
    """Multi-year climate series and baseline climatology for a spatial unit."""

    unit_id: str
    name: str
    country: str
    role: str
    eligible: bool
    chirps_pixel_count: int
    baseline_period: tuple[int, int]
    baseline_mean_rainfall_mm: float
    baseline_std_rainfall_mm: float
    baseline_interannual_cv: float
    baseline_mean_wet_season_mm: float
    baseline_mean_temp_c: float | None
    baseline_std_temp_c: float | None
    pre_treatment_mean_rainfall_mm: float | None
    post_treatment_mean_rainfall_mm: float | None
    pre_treatment_std_rainfall_mm: float | None
    post_treatment_std_rainfall_mm: float | None
    pre_treatment_drought_years: tuple[int, ...]
    post_treatment_drought_years: tuple[int, ...]
    records: tuple[AnnualClimateRecord, ...]
    missing_years: tuple[int, ...]
    incomplete_years: tuple[int, ...]

    def record_by_year(self) -> dict[int, AnnualClimateRecord]:
        """Return a mapping from calendar year to AnnualClimateRecord."""
        return {r.year: r for r in self.records}


@dataclass(frozen=True)
class AlignedClimateObservation:
    """A single year where satellite observation and climate covariates are aligned."""

    year: int
    satellite_value: float
    annual_rainfall_mm: float | None
    wet_season_rainfall_mm: float | None
    dry_season_rainfall_mm: float | None
    rainfall_anomaly_mm: float | None
    rainfall_anomaly_z: float | None
    spi_12: float | None
    spi_6_wet: float | None
    drought_classification: str
    mean_temp_c: float | None
    max_temp_c: float | None
    temp_anomaly_c: float | None
    is_complete_climate_year: bool
    missing_climate_months: tuple[int, ...]


@dataclass(frozen=True)
class TemporalAlignmentReport:
    """Explicit diagnostic report aligning climate records with satellite observations."""

    unit_id: str
    satellite_indicator: str
    satellite_years: tuple[int, ...]
    climate_complete_years: tuple[int, ...]
    aligned_years: tuple[int, ...]
    missing_climate_years: tuple[int, ...]
    incomplete_climate_years: tuple[int, ...]
    climate_only_years: tuple[int, ...]
    chirts_uncovered_years: tuple[int, ...]
    alignment_status: str
    interpolation_applied: bool
    aligned_records: tuple[AlignedClimateObservation, ...]
    notes: tuple[str, ...]


@dataclass(frozen=True)
class KaribaClimateBundle:
    """Complete climate dataset and provenance bundle for Kariba and donor districts."""

    case_id: str
    retrieved_at: str
    sha256: str
    spatial_window_bbox: tuple[float, float, float, float]
    spatial_window_shape: tuple[int, int]
    sources: Mapping[str, ClimateSourceProvenance]
    s3_mirror_missing_months: tuple[str, ...]
    missing_months_after_upstream: tuple[str, ...]
    eligible_donor_ids: tuple[str, ...]
    unit_summaries: Mapping[str, UnitClimateSummary]

    @property
    def treated_summary(self) -> UnitClimateSummary:
        """Return the UnitClimateSummary for the treated Kariba AOI."""
        return self.unit_summaries["kariba-redd"]

    def eligible_donor_summaries(self) -> dict[str, UnitClimateSummary]:
        """Return summaries for the 37 spatially eligible donor districts."""
        return {
            uid: self.unit_summaries[uid]
            for uid in self.eligible_donor_ids
            if uid in self.unit_summaries
        }


def classify_spi_drought(spi_value: float | None) -> str:
    """Classify Standardized Precipitation Index (SPI) per WMO (2012) thresholds."""
    if spi_value is None or not math.isfinite(spi_value):
        return "insufficient_data"
    if spi_value <= -2.0:
        return "extreme_drought"
    if spi_value <= -1.5:
        return "severe_drought"
    if spi_value <= -1.0:
        return "moderate_drought"
    if spi_value < 1.0:
        return "near_normal"
    if spi_value < 1.5:
        return "moderately_wet"
    if spi_value < 2.0:
        return "very_wet"
    return "extremely_wet"


_STD_NORMAL = statistics.NormalDist(0.0, 1.0)


def _regularized_gamma_p(a: float, x: float) -> float:
    """Compute regularized lower incomplete gamma function P(a, x) for a > 0, x >= 0."""
    if x <= 0.0:
        return 0.0
    if a <= 0.0:
        raise ValueError(f"Gamma shape parameter must be positive: {a}")

    gln = math.lgamma(a)
    if x < a + 1.0:
        # Series representation
        ap = a
        total = 1.0 / a
        delta = total
        for _ in range(200):
            ap += 1.0
            delta *= x / ap
            total += delta
            if abs(delta) < abs(total) * 1e-14:
                break
        return min(max(total * math.exp(-x + a * math.log(x) - gln), 0.0), 1.0)

    # Continued-fraction representation (Lentz's method) for Q(a, x) = 1 - P(a, x)
    b = x + 1.0 - a
    c = 1.0 / 1e-30
    d = 1.0 / b
    h = d
    for i in range(1, 201):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < 1e-30:
            d = 1e-30
        c = b + an / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-14:
            break
    q_val = math.exp(-x + a * math.log(x) - gln) * h
    return min(max(1.0 - q_val, 0.0), 1.0)


def compute_gamma_spi(
    values: Sequence[float | None],
    baseline_mask: Sequence[bool],
    *,
    min_baseline_years: int = 20,
) -> list[float | None]:
    """Compute Standardized Precipitation Index (SPI) via two-parameter Gamma fitting.

    Follows McKee et al. (1993), Thom (1958), and WMO (2012):
    - Fits a two-parameter Gamma distribution (with zero-precipitation probability mass q)
      strictly on the reference baseline subset (`baseline_mask[t] == True`) so post-treatment
      shocks do not contaminate the baseline distribution parameters.
    - Refuses to fabricate SPI (returns all None) if fewer than ``min_baseline_years`` valid
      baseline observations exist.
    """
    if len(values) != len(baseline_mask):
        raise ValueError("values and baseline_mask must have identical length.")

    baseline_vals = np.array(
        [
            float(v)
            for v, is_base in zip(values, baseline_mask, strict=True)
            if is_base and v is not None and math.isfinite(v) and v >= 0.0
        ],
        dtype=np.float64,
    )
    n_base = baseline_vals.size
    if n_base < min_baseline_years:
        return [None for _ in values]

    pos_base = baseline_vals[baseline_vals > 0.0]
    if pos_base.size < min_baseline_years:
        return [None for _ in values]

    # Probability of zero rainfall in baseline
    q_zero = float(np.sum(baseline_vals == 0.0)) / float(n_base)

    # Thom (1958) / WMO (2012) maximum-likelihood approximation on positive baseline rainfall
    mean_pos = float(np.mean(pos_base))
    std_pos = float(np.std(pos_base, ddof=1))
    if std_pos <= 1e-9 or mean_pos <= 1e-9:
        return [None for _ in values]

    a_thom = math.log(mean_pos) - float(np.mean(np.log(pos_base)))
    if a_thom > 1e-12:
        shape_alpha = (1.0 + math.sqrt(1.0 + 4.0 * a_thom / 3.0)) / (4.0 * a_thom)
        scale_beta = mean_pos / shape_alpha
    else:
        shape_alpha = (mean_pos / std_pos) ** 2
        scale_beta = (std_pos**2) / mean_pos

    out: list[float | None] = []
    # Clamp cumulative probability away from {0, 1} to keep SPI within [-3.5, +3.5]
    eps = 1e-4
    for v in values:
        if v is None or not math.isfinite(v) or v < 0.0:
            out.append(None)
            continue
        if v == 0.0:
            cdf_h = q_zero
        else:
            g_x = _regularized_gamma_p(shape_alpha, float(v) / scale_beta)
            cdf_h = q_zero + (1.0 - q_zero) * g_x
        cdf_clamped = min(max(cdf_h, eps), 1.0 - eps)
        z_spi = float(_STD_NORMAL.inv_cdf(cdf_clamped))
        out.append(round(z_spi, 4))
    return out


def build_unit_climate_summary(
    *,
    unit_id: str,
    name: str,
    country: str,
    role: str,
    eligible: bool,
    chirps_pixel_count: int,
    monthly_precip_mm: Mapping[str, float],
    monthly_t2m_c: Mapping[str, float] | None = None,
    monthly_t2m_max_c: Mapping[str, float] | None = None,
    monthly_t2m_min_c: Mapping[str, float] | None = None,
    years: Sequence[int] = tuple(range(1981, 2024)),
    baseline_period: tuple[int, int] = (1981, 2010),
    pre_treatment_period: tuple[int, int] = (2001, 2010),
    post_treatment_period: tuple[int, int] = (2011, 2022),
    chirts_coverage_period: tuple[int, int] = (1983, 2016),
    min_spi_baseline_years: int = 20,
    input_precip_unit: str = "mm/month",
    input_temp_unit: str = "degC",
) -> UnitClimateSummary:
    """Aggregate monthly climate observations into annual/seasonal records and drought indices.

    Explicitly tracks missing months and refuses to silently interpolate incomplete years.
    """
    t2m_map = monthly_t2m_c or {}
    tmax_map = monthly_t2m_max_c or {}
    tmin_map = monthly_t2m_min_c or {}

    years_sorted = sorted(set(int(y) for y in years))
    b_start, b_end = baseline_period

    raw_annual: list[float | None] = []
    raw_partial: list[float | None] = []
    raw_wet_austral: list[float | None] = []
    raw_wet_cal: list[float | None] = []
    raw_dry: list[float | None] = []
    raw_peak_jfm: list[float | None] = []
    raw_m_std: list[float | None] = []
    raw_m_cv: list[float | None] = []
    raw_t2m: list[float | None] = []
    raw_tmax: list[float | None] = []
    raw_tmin: list[float | None] = []
    valid_month_counts: list[int] = []
    missing_months_per_year: list[tuple[int, ...]] = []
    missing_years: list[int] = []
    incomplete_years: list[int] = []

    days_per_month = {1: 31, 2: 28, 3: 31, 4: 30, 5: 31, 6: 30, 7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31}

    def _get_precip_mm(y: int, m: int) -> float | None:
        ym = f"{y}.{m:02d}"
        if ym not in monthly_precip_mm:
            return None
        val = monthly_precip_mm[ym]
        if val is None or not math.isfinite(val) or val < 0.0:
            return None
        if input_precip_unit == "mm/month" or input_precip_unit == "mm":
            return float(val)
        return convert_climate_unit(
            float(val),
            input_precip_unit,
            "mm/month",
            days_in_month=days_per_month[m],
        )

    def _get_temp_c(src: Mapping[str, float], y: int, m: int) -> float | None:
        ym = f"{y}.{m:02d}"
        if ym not in src:
            return None
        val = src[ym]
        if val is None or not math.isfinite(val):
            return None
        return convert_climate_unit(float(val), input_temp_unit, "degC")

    for y in years_sorted:
        m_vals: dict[int, float] = {}
        missing_m: list[int] = []
        for m in range(1, 13):
            pv = _get_precip_mm(y, m)
            if pv is None:
                missing_m.append(m)
            else:
                m_vals[m] = pv

        v_count = len(m_vals)
        valid_month_counts.append(v_count)
        missing_months_per_year.append(tuple(missing_m))

        if v_count == 0:
            missing_years.append(y)
            raw_annual.append(None)
            raw_partial.append(None)
            raw_m_std.append(None)
            raw_m_cv.append(None)
        elif v_count < 12:
            incomplete_years.append(y)
            # Do NOT fabricate a 12-month total from fewer than 12 months
            raw_annual.append(None)
            raw_partial.append(round(float(sum(m_vals.values())), 3))
            raw_m_std.append(None)
            raw_m_cv.append(None)
        else:
            arr_m = np.array([m_vals[m] for m in range(1, 13)], dtype=np.float64)
            tot = float(np.sum(arr_m))
            std_m = float(np.std(arr_m, ddof=1))
            mean_m = float(np.mean(arr_m))
            raw_annual.append(round(tot, 3))
            raw_partial.append(round(tot, 3))
            raw_m_std.append(round(std_m, 3))
            raw_m_cv.append(round(std_m / mean_m, 4) if mean_m > 1e-6 else 0.0)

        # Austral wet season: Nov(y-1), Dec(y-1), Jan(y), Feb(y), Mar(y), Apr(y)
        prev_nov = _get_precip_mm(y - 1, 11)
        prev_dec = _get_precip_mm(y - 1, 12)
        jan_apr = [m_vals.get(m) for m in (1, 2, 3, 4)]
        if prev_nov is not None and prev_dec is not None and all(v is not None for v in jan_apr):
            wet_aus = prev_nov + prev_dec + sum(float(v) for v in jan_apr if v is not None)
            raw_wet_austral.append(round(float(wet_aus), 3))
        else:
            raw_wet_austral.append(None)

        # Calendar wet months: Jan..Apr + Nov..Dec of year y
        cal_wet_list = [m_vals.get(m) for m in (1, 2, 3, 4, 11, 12)]
        if all(v is not None for v in cal_wet_list):
            raw_wet_cal.append(round(float(sum(float(v) for v in cal_wet_list if v is not None)), 3))
        else:
            raw_wet_cal.append(None)

        # Dry season: May..Oct of year y
        dry_list = [m_vals.get(m) for m in (5, 6, 7, 8, 9, 10)]
        if all(v is not None for v in dry_list):
            raw_dry.append(round(float(sum(float(v) for v in dry_list if v is not None)), 3))
        else:
            raw_dry.append(None)

        # Peak wet season 3-month (Jan-Feb-Mar)
        jfm_list = [m_vals.get(m) for m in (1, 2, 3)]
        if all(v is not None for v in jfm_list):
            raw_peak_jfm.append(round(float(sum(float(v) for v in jfm_list if v is not None)), 3))
        else:
            raw_peak_jfm.append(None)

        # Annual temperatures (require all 12 months to avoid seasonal bias!)
        t2m_12 = [_get_temp_c(t2m_map, y, m) for m in range(1, 13)]
        tmax_12 = [_get_temp_c(tmax_map, y, m) for m in range(1, 13)]
        tmin_12 = [_get_temp_c(tmin_map, y, m) for m in range(1, 13)]
        raw_t2m.append(
            round(float(np.mean([v for v in t2m_12 if v is not None])), 3)
            if all(v is not None for v in t2m_12)
            else None
        )
        raw_tmax.append(
            round(float(np.mean([v for v in tmax_12 if v is not None])), 3)
            if all(v is not None for v in tmax_12)
            else None
        )
        raw_tmin.append(
            round(float(np.mean([v for v in tmin_12 if v is not None])), 3)
            if all(v is not None for v in tmin_12)
            else None
        )

    baseline_mask = [b_start <= y <= b_end for y in years_sorted]
    base_rain_vals = np.array(
        [v for v, is_b in zip(raw_annual, baseline_mask, strict=True) if is_b and v is not None],
        dtype=np.float64,
    )
    if base_rain_vals.size < 2:
        raise InsufficientDataError(
            f"Unit {unit_id!r} has only {base_rain_vals.size} complete baseline rainfall years "
            f"in {baseline_period}; at least 2 are required for baseline mean/std."
        )

    base_rain_mean = float(np.mean(base_rain_vals))
    base_rain_std = float(np.std(base_rain_vals, ddof=1))
    base_rain_cv = base_rain_std / base_rain_mean if base_rain_mean > 1e-6 else 0.0

    base_wet_vals = np.array(
        [
            v if v is not None else cw
            for v, cw, is_b in zip(raw_wet_austral, raw_wet_cal, baseline_mask, strict=True)
            if is_b and (v is not None or cw is not None)
        ],
        dtype=np.float64,
    )
    base_wet_mean = float(np.mean(base_wet_vals)) if base_wet_vals.size > 0 else 0.0

    base_temp_vals = np.array(
        [v for v, is_b in zip(raw_t2m, baseline_mask, strict=True) if is_b and v is not None],
        dtype=np.float64,
    )
    base_temp_mean = float(np.mean(base_temp_vals)) if base_temp_vals.size >= 2 else None
    base_temp_std = float(np.std(base_temp_vals, ddof=1)) if base_temp_vals.size >= 2 else None

    # Compute SPI-12, SPI-6 (wet season), and SPI-3 (peak JFM)
    spi_12_list = compute_gamma_spi(
        raw_annual, baseline_mask, min_baseline_years=min_spi_baseline_years
    )
    # For SPI-6 wet season, use Austral wet season where available (or calendar wet months if 1981)
    wet_for_spi = [
        v if v is not None else cw
        for v, cw in zip(raw_wet_austral, raw_wet_cal, strict=True)
    ]
    spi_6_list = compute_gamma_spi(
        wet_for_spi, baseline_mask, min_baseline_years=min_spi_baseline_years
    )
    spi_3_list = compute_gamma_spi(
        raw_peak_jfm, baseline_mask, min_baseline_years=min_spi_baseline_years
    )

    records: list[AnnualClimateRecord] = []
    for idx, y in enumerate(years_sorted):
        ann = raw_annual[idx]
        anom_mm = round(ann - base_rain_mean, 3) if ann is not None else None
        anom_pct = (
            round(100.0 * (ann - base_rain_mean) / base_rain_mean, 2)
            if (ann is not None and base_rain_mean > 1e-6)
            else None
        )
        anom_z = (
            round((ann - base_rain_mean) / base_rain_std, 4)
            if (ann is not None and base_rain_std > 1e-6)
            else None
        )

        t_val = raw_t2m[idx]
        t_anom = (
            round(t_val - base_temp_mean, 3)
            if (t_val is not None and base_temp_mean is not None)
            else None
        )
        t_anom_z = (
            round((t_val - base_temp_mean) / base_temp_std, 4)
            if (t_val is not None and base_temp_mean is not None and base_temp_std and base_temp_std > 1e-6)
            else None
        )

        spi12 = spi_12_list[idx]
        # If SPI-12 is None (e.g. 2023 if Dec was missing on S3 mirror, though SPI-6 wet season is complete!),
        # classify based on SPI-12 if available else SPI-6 wet season
        drought_spi_ref = spi12 if spi12 is not None else spi_6_list[idx]
        d_class = classify_spi_drought(drought_spi_ref)

        records.append(
            AnnualClimateRecord(
                unit_id=unit_id,
                year=y,
                valid_months=valid_month_counts[idx],
                missing_months=missing_months_per_year[idx],
                is_complete_year=(valid_month_counts[idx] == 12),
                annual_rainfall_mm=ann,
                partial_year_rainfall_mm=raw_partial[idx],
                wet_season_rainfall_mm=raw_wet_austral[idx],
                calendar_wet_months_mm=raw_wet_cal[idx],
                dry_season_rainfall_mm=raw_dry[idx],
                rainfall_anomaly_mm=anom_mm,
                rainfall_anomaly_pct=anom_pct,
                rainfall_anomaly_z=anom_z,
                intra_annual_monthly_std_mm=raw_m_std[idx],
                intra_annual_cv=raw_m_cv[idx],
                spi_12=spi12,
                spi_6_wet=spi_6_list[idx],
                spi_3_peak=spi_3_list[idx],
                drought_classification=d_class,
                mean_temp_c=t_val,
                max_temp_c=raw_tmax[idx],
                min_temp_c=raw_tmin[idx],
                temp_anomaly_c=t_anom,
                temp_anomaly_z=t_anom_z,
                chirts_tmax_available=(chirts_coverage_period[0] <= y <= chirts_coverage_period[1]),
            )
        )

    pre_s, pre_e = pre_treatment_period
    post_s, post_e = post_treatment_period
    pre_rain = [r.annual_rainfall_mm for r in records if pre_s <= r.year <= pre_e and r.annual_rainfall_mm is not None]
    post_rain = [r.annual_rainfall_mm for r in records if post_s <= r.year <= post_e and r.annual_rainfall_mm is not None]

    pre_drought = tuple(
        r.year
        for r in records
        if pre_s <= r.year <= pre_e
        and ((r.spi_12 is not None and r.spi_12 <= -1.0) or (r.spi_12 is None and r.spi_6_wet is not None and r.spi_6_wet <= -1.0))
    )
    post_drought = tuple(
        r.year
        for r in records
        if r.year >= post_s
        and ((r.spi_12 is not None and r.spi_12 <= -1.0) or (r.spi_12 is None and r.spi_6_wet is not None and r.spi_6_wet <= -1.0))
    )

    return UnitClimateSummary(
        unit_id=unit_id,
        name=name,
        country=country,
        role=role,
        eligible=eligible,
        chirps_pixel_count=chirps_pixel_count,
        baseline_period=baseline_period,
        baseline_mean_rainfall_mm=round(base_rain_mean, 3),
        baseline_std_rainfall_mm=round(base_rain_std, 3),
        baseline_interannual_cv=round(base_rain_cv, 4),
        baseline_mean_wet_season_mm=round(base_wet_mean, 3),
        baseline_mean_temp_c=round(base_temp_mean, 3) if base_temp_mean is not None else None,
        baseline_std_temp_c=round(base_temp_std, 3) if base_temp_std is not None else None,
        pre_treatment_mean_rainfall_mm=round(float(np.mean(pre_rain)), 3) if pre_rain else None,
        post_treatment_mean_rainfall_mm=round(float(np.mean(post_rain)), 3) if post_rain else None,
        pre_treatment_std_rainfall_mm=round(float(np.std(pre_rain, ddof=1)), 3) if len(pre_rain) >= 2 else None,
        post_treatment_std_rainfall_mm=round(float(np.std(post_rain, ddof=1)), 3) if len(post_rain) >= 2 else None,
        pre_treatment_drought_years=pre_drought,
        post_treatment_drought_years=post_drought,
        records=tuple(records),
        missing_years=tuple(missing_years),
        incomplete_years=tuple(incomplete_years),
    )


def align_climate_to_satellite_years(
    climate_summary: UnitClimateSummary,
    satellite_years: Sequence[int],
    satellite_values: Sequence[float],
    *,
    satellite_indicator: str = "NDVI",
    require_complete_climate_years: bool = False,
) -> TemporalAlignmentReport:
    """Align annual climate observations with a satellite time series without silent interpolation.

    Args:
        climate_summary: Aggregated climate records for the spatial unit.
        satellite_years: Years present in the satellite observation series.
        satellite_values: Observed satellite indicator values corresponding to ``satellite_years``.
        satellite_indicator: Name of the satellite index (e.g. ``"NDVI"``).
        require_complete_climate_years: If True, raises :class:`DataUnavailableError` when any
            requested satellite year lacks a complete 12-month climate record.
    """
    if len(satellite_years) != len(satellite_values):
        raise ValueError("satellite_years and satellite_values must have equal length.")

    rec_by_year = climate_summary.record_by_year()
    sat_map = {int(y): float(v) for y, v in zip(satellite_years, satellite_values, strict=True)}
    sat_years_sorted = tuple(sorted(sat_map.keys()))

    complete_clim_years = tuple(
        sorted(r.year for r in climate_summary.records if r.is_complete_year)
    )
    aligned_years: list[int] = []
    missing_clim: list[int] = []
    incomplete_clim: list[int] = []
    chirts_uncovered: list[int] = []
    aligned_obs: list[AlignedClimateObservation] = []

    for y in sat_years_sorted:
        r = rec_by_year.get(y)
        if r is None or r.valid_months == 0:
            missing_clim.append(y)
            continue
        if not r.chirts_tmax_available:
            chirts_uncovered.append(y)
        if not r.is_complete_year:
            incomplete_clim.append(y)
            if require_complete_climate_years:
                raise DataUnavailableError(
                    f"Unit {climate_summary.unit_id!r} has incomplete climate coverage in year {y} "
                    f"(missing months: {r.missing_months}); refusing to interpolate."
                )
        aligned_years.append(y)
        aligned_obs.append(
            AlignedClimateObservation(
                year=y,
                satellite_value=sat_map[y],
                annual_rainfall_mm=r.annual_rainfall_mm,
                wet_season_rainfall_mm=r.wet_season_rainfall_mm,
                dry_season_rainfall_mm=r.dry_season_rainfall_mm,
                rainfall_anomaly_mm=r.rainfall_anomaly_mm,
                rainfall_anomaly_z=r.rainfall_anomaly_z,
                spi_12=r.spi_12,
                spi_6_wet=r.spi_6_wet,
                drought_classification=r.drought_classification,
                mean_temp_c=r.mean_temp_c,
                max_temp_c=r.max_temp_c,
                temp_anomaly_c=r.temp_anomaly_c,
                is_complete_climate_year=r.is_complete_year,
                missing_climate_months=r.missing_months,
            )
        )

    if require_complete_climate_years and missing_clim:
        raise DataUnavailableError(
            f"Unit {climate_summary.unit_id!r} is missing climate data for satellite years: {missing_clim}."
        )

    clim_only = tuple(
        sorted(set(r.year for r in climate_summary.records if r.valid_months > 0) - set(sat_years_sorted))
    )

    if not aligned_years:
        status = "DISJOINT"
    elif missing_clim or incomplete_clim:
        status = "PARTIAL"
    else:
        status = "COMPLETE"

    notes: list[str] = [
        f"Satellite window covers {len(sat_years_sorted)} years ({sat_years_sorted[0]}..{sat_years_sorted[-1]})"
        if sat_years_sorted
        else "Satellite window is empty.",
        "No missing months or years were interpolated.",
    ]
    if missing_clim:
        notes.append(f"Missing climate years in satellite window: {missing_clim}.")
    if incomplete_clim:
        notes.append(
            f"Incomplete (<12-month) climate years in satellite window: {incomplete_clim}; "
            "12-month annual totals and SPI-12 are withheld (None) for incomplete years while "
            "complete 6-month Austral wet-season totals (Nov-Apr) and SPI-6 are preserved."
        )
    if chirts_uncovered:
        notes.append(
            f"CHIRTSmax v1.0 CDR (1983-2016) does not cover years {chirts_uncovered}; "
            "temperature covariates for those years rely on NASA POWER MERRA-2 (1981-2023)."
        )

    return TemporalAlignmentReport(
        unit_id=climate_summary.unit_id,
        satellite_indicator=satellite_indicator,
        satellite_years=sat_years_sorted,
        climate_complete_years=complete_clim_years,
        aligned_years=tuple(aligned_years),
        missing_climate_years=tuple(missing_clim),
        incomplete_climate_years=tuple(incomplete_clim),
        climate_only_years=clim_only,
        chirts_uncovered_years=tuple(chirts_uncovered),
        alignment_status=status,
        interpolation_applied=False,
        aligned_records=tuple(aligned_obs),
        notes=tuple(notes),
    )


def load_kariba_climate_bundle(
    cache_path: Path | None = None,
    *,
    baseline_period: tuple[int, int] = (1981, 2010),
    pre_treatment_period: tuple[int, int] = (2001, 2010),
    post_treatment_period: tuple[int, int] = (2011, 2022),
) -> KaribaClimateBundle:
    """Load the persisted Kariba CHIRPS + NASA POWER climate bundle and compute unit summaries."""
    path = cache_path or DEFAULT_CLIMATE_CACHE_PATH
    if not path.exists():
        raise DataUnavailableError(
            f"Kariba climate bundle not found at {path}. Run climate ingestion first."
        )

    raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    src_raw = raw["sources"]
    chirps_meta = src_raw["chirps_v2_monthly"]
    power_meta = src_raw["nasa_power_merra2_monthly"]
    chirts_meta = src_raw["chirts_max_cdr_reference"]

    s3_missing = tuple(chirps_meta.get("s3_mirror_missing_months", ()))
    upstream_missing = tuple(chirps_meta.get("missing_months_after_upstream", ()))

    sources: dict[str, ClimateSourceProvenance] = {
        "chirps_v2_monthly": ClimateSourceProvenance(
            dataset_id=chirps_meta["dataset_id"],
            provider=chirps_meta["provider"],
            source_uri=chirps_meta["primary_mirror_uri"],
            resolution_deg=float(chirps_meta["resolution_deg"]),
            resolution_km=float(chirps_meta["resolution_km"]),
            crs=chirps_meta["crs"],
            native_unit=chirps_meta["native_unit"],
            canonical_unit="mm/year",
            temporal_coverage_start="1981-01",
            temporal_coverage_end="2023-12",
            retrieved_at=raw["retrieved_at"],
            citation=chirps_meta["citation"],
            processing_steps=(
                "1. Windowed read of 0.05° WGS84 CHIRPS v2.0 monthly COGs over [21.95E..33.55E, 22.50S..8.15S].",
                "2. Exact polygon zonal masking (rasterio.features.geometry_mask, all_touched=True) for Kariba AOI and 50 ADM2 districts (37 spatially eligible donors).",
                "3. Exclusion of nodata pixels (< 0) and computation of monthly polygon spatial mean and spatial standard deviation.",
                "4. Aggregation to calendar-year (Jan-Dec) and Austral hydrological wet-season (Nov[t-1]-Apr[t]) and dry-season (May-Oct) totals without interpolating missing months.",
                "5. Two-parameter Gamma SPI-12, SPI-6 (wet), and SPI-3 (JFM) calibration against the 30-year pre-treatment WMO reference baseline (1981-2010).",
            ),
            known_coverage_gaps=(
                tuple(
                    f"DE Africa S3 mirror missing monthly COGs {list(s3_missing)}; "
                    f"unresolved after upstream query: {list(upstream_missing)}"
                    for _ in [1]
                    if s3_missing
                )
            ),
        ),
        "nasa_power_merra2_monthly": ClimateSourceProvenance(
            dataset_id=power_meta["dataset_id"],
            provider=power_meta["provider"],
            source_uri=power_meta["source_uri"],
            resolution_deg=float(power_meta["resolution_deg_lat"]),
            resolution_km=55.0,
            crs=power_meta["crs"],
            native_unit=power_meta["native_unit"],
            canonical_unit="degC",
            temporal_coverage_start="1981-01",
            temporal_coverage_end="2023-12",
            retrieved_at=raw["retrieved_at"],
            citation="NASA Langley Research Center POWER Project / GMAO MERRA-2 (Gelaro et al., 2017).",
            processing_steps=(
                "1. Regional monthly query for T2M, T2M_MAX, T2M_MIN across Zimbabwe and Zambia (1981-2023).",
                "2. Spatial matching of 0.5° x 0.625° MERRA-2 grid cells to each AOI/ADM2 polygon bounding box and centroid.",
                "3. Aggregation of complete 12-month calendar years to annual mean, mean-maximum, and mean-minimum temperature (degC) and anomalies vs 1981-2010 baseline.",
            ),
            known_coverage_gaps=(),
        ),
        "chirts_max_cdr_reference": ClimateSourceProvenance(
            dataset_id=chirts_meta["dataset_id"],
            provider=chirts_meta["provider"],
            source_uri=chirts_meta["source_uri"],
            resolution_deg=float(chirts_meta["resolution_deg"]),
            resolution_km=5.5,
            crs="EPSG:4326",
            native_unit=chirts_meta["native_unit"],
            canonical_unit="degC",
            temporal_coverage_start="1983-01",
            temporal_coverage_end="2016-12",
            retrieved_at=raw["retrieved_at"],
            citation="Funk, C., et al. (2019). A High-Resolution 1983–2016 Tmax Climate Data Record Based on Infrared Temperatures and Stations by the Climate Hazards Center. Journal of Climate, 32(17), 5639-5658.",
            processing_steps=(
                "Evaluated temporal horizon (1983-01 to 2016-12); documented post-2016 archive cutoff covering late post-treatment (2017-2022) and Sentinel-2 (2021-2023) windows.",
            ),
            known_coverage_gaps=(chirts_meta["coverage_limitation"],),
        ),
    }

    unit_summaries: dict[str, UnitClimateSummary] = {}
    for uid, udata in raw["units"].items():
        unit_summaries[uid] = build_unit_climate_summary(
            unit_id=uid,
            name=udata["name"],
            country=udata["country"],
            role=udata["role"],
            eligible=bool(udata["eligible"]),
            chirps_pixel_count=int(udata["chirps_pixel_count"]),
            monthly_precip_mm=udata["monthly_precip_mm"],
            monthly_t2m_c=udata.get("monthly_t2m_c", {}),
            monthly_t2m_max_c=udata.get("monthly_t2m_max_c", {}),
            monthly_t2m_min_c=udata.get("monthly_t2m_min_c", {}),
            baseline_period=baseline_period,
            pre_treatment_period=pre_treatment_period,
            post_treatment_period=post_treatment_period,
        )

    bbox_raw = raw["spatial_Window_bbox"]
    shape_raw = raw["spatial_window_shape"]
    return KaribaClimateBundle(
        case_id=raw["case_id"],
        retrieved_at=raw["retrieved_at"],
        sha256=raw["sha256"],
        spatial_window_bbox=(
            float(bbox_raw[0]),
            float(bbox_raw[1]),
            float(bbox_raw[2]),
            float(bbox_raw[3]),
        ),
        spatial_window_shape=(int(shape_raw[0]), int(shape_raw[1])),
        sources=sources,
        s3_mirror_missing_months=s3_missing,
        missing_months_after_upstream=upstream_missing,
        eligible_donor_ids=tuple(raw["eligible_donor_ids"]),
        unit_summaries=unit_summaries,
    )
