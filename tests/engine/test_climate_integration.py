"""Comprehensive scientific-integrity and unit tests for climate data integration
and time-varying confounder diagnostics (Task 3).

Tests cover:
1. Climate unit family enforcement and unit conversions (precipitation, temperature, drought indices).
2. Missing climate observations and explicit refusal to silently interpolate incomplete years.
3. Temporal alignment between satellite observation periods (2001-2022, 2021-2023) and climate archives.
4. Standardized Precipitation Index (SPI) calculation and real Kariba CHIRPS/NASA POWER bundle integrity.
5. Donor climate comparability diagnostics and covariate balance checks.
6. Adjusted vs unadjusted causal estimation without modifying core estimators (`fit_synthetic_control`, `estimate_did`).
7. Strict preservation of causal identification gates (`VerdictLabel.INCONCLUSIVE` retained under J > T0, degenerate weights, poor pre-fit, or uncalibrated biomass).
"""

from __future__ import annotations

import inspect

import numpy as np
import pytest

from groundtruth.contracts.errors import DataUnavailableError
from groundtruth.contracts.ports import ObservationSpec
from groundtruth.contracts.request import UnitRef
from groundtruth.contracts.types import Indicator, VerdictLabel
from groundtruth.contracts.units import (
    UnitFamily,
    celsius_to_kelvin,
    convert_climate_unit,
    kelvin_to_celsius,
    meters_to_mm,
    mm_per_day_to_mm_per_month,
    unit_family,
)
from groundtruth.data_access.climate import (
    DEFAULT_CLIMATE_CACHE_PATH,
    align_climate_to_satellite_years,
    build_unit_climate_summary,
    classify_spi_drought,
    compute_gamma_spi,
    load_kariba_climate_bundle,
)
from groundtruth.engine.causal.climate_confounding import (
    analyze_sentinel2_climate_comovement,
    build_climate_covariate_matrices,
    check_post_treatment_covariate_divergence,
    evaluate_causal_gates_for_spec,
    evaluate_donor_climate_comparability,
    run_climate_confounding_analysis,
)
from groundtruth.engine.causal.did import estimate_did
from groundtruth.engine.causal.synthetic_control import (
    SyntheticControlFit,
    fit_synthetic_control,
)
from groundtruth.platform.datasets.access import SyntheticFixtureObservationAccess

# ============================================================================
# 1. UNIT CONVERSIONS & DIMENSIONAL INTEGRITY
# ============================================================================


class TestClimateUnitConversions:
    """Verify climate unit family registration, conversions, and cross-family rejection."""

    def test_climate_unit_families_registered(self) -> None:
        assert unit_family("mm") == UnitFamily.PRECIPITATION
        assert unit_family("mm/year") == UnitFamily.PRECIPITATION
        assert unit_family("mm/season") == UnitFamily.PRECIPITATION
        assert unit_family("mm/month") == UnitFamily.PRECIPITATION
        assert unit_family("mm/day") == UnitFamily.PRECIPITATION
        assert unit_family("m") == UnitFamily.PRECIPITATION
        assert unit_family("degC") == UnitFamily.TEMPERATURE
        assert unit_family("K") == UnitFamily.TEMPERATURE
        assert unit_family("degC_anomaly") == UnitFamily.TEMPERATURE
        assert unit_family("spi") == UnitFamily.DROUGHT_INDEX
        assert unit_family("spei") == UnitFamily.DROUGHT_INDEX
        assert unit_family("z_score") == UnitFamily.DROUGHT_INDEX
        assert unit_family("cv") == UnitFamily.DROUGHT_INDEX
        assert unit_family("ndmi") == UnitFamily.INDEX

    def test_kelvin_celsius_round_trip(self) -> None:
        assert pytest.approx(kelvin_to_celsius(273.15), abs=1e-9) == 0.0
        assert pytest.approx(kelvin_to_celsius(296.298), abs=1e-6) == 23.148
        assert pytest.approx(celsius_to_kelvin(23.148), abs=1e-6) == 296.298
        assert pytest.approx(kelvin_to_celsius(celsius_to_kelvin(-15.5)), abs=1e-9) == -15.5

    def test_physical_bounds_rejected_for_temperature_and_precipitation(self) -> None:
        with pytest.raises(ValueError, match="cannot be negative"):
            kelvin_to_celsius(-1.0)
        with pytest.raises(ValueError, match="below absolute zero"):
            celsius_to_kelvin(-274.0)
        with pytest.raises(ValueError, match="cannot be negative"):
            meters_to_mm(-0.01)
        with pytest.raises(ValueError, match="cannot be negative"):
            mm_per_day_to_mm_per_month(-2.0, 30)
        with pytest.raises(ValueError, match="days_in_month"):
            mm_per_day_to_mm_per_month(5.0, 27)

    def test_precipitation_unit_conversions(self) -> None:
        assert pytest.approx(meters_to_mm(0.694277), abs=1e-6) == 694.277
        assert pytest.approx(mm_per_day_to_mm_per_month(4.5, 31), abs=1e-6) == 139.5
        assert (
            pytest.approx(
                convert_climate_unit(0.5, "m", "mm"),
                abs=1e-6,
            )
            == 500.0
        )
        assert (
            pytest.approx(
                convert_climate_unit(500.0, "mm", "m"),
                abs=1e-6,
            )
            == 0.5
        )
        assert (
            pytest.approx(
                convert_climate_unit(3.0, "mm/day", "mm/month", days_in_month=30),
                abs=1e-6,
            )
            == 90.0
        )
        assert (
            pytest.approx(
                convert_climate_unit(90.0, "mm/month", "mm/day", days_in_month=30),
                abs=1e-6,
            )
            == 3.0
        )

    def test_mm_per_day_requires_days_in_month(self) -> None:
        with pytest.raises(ValueError, match="requires days_in_month"):
            convert_climate_unit(3.0, "mm/day", "mm/month")

    def test_cross_family_conversions_strictly_rejected(self) -> None:
        with pytest.raises(ValueError, match="Refusing cross-family unit conversion"):
            convert_climate_unit(700.0, "mm", "tCO2e")
        with pytest.raises(ValueError, match="Refusing cross-family unit conversion"):
            convert_climate_unit(23.5, "degC", "ndvi")
        with pytest.raises(ValueError, match="Refusing cross-family unit conversion"):
            convert_climate_unit(-1.5, "spi", "mm")


# ============================================================================
# 2. MISSING CLIMATE OBSERVATIONS & EXPLICIT REFUSAL TO INTERPOLATE
# ============================================================================


class TestMissingClimateObservations:
    """Verify missing monthly observations are tracked and never silently interpolated."""

    def test_incomplete_calendar_year_withholds_annual_total_and_spi12(self) -> None:
        rng = np.random.default_rng(12345)
        monthly_rain: dict[str, float] = {}
        monthly_temp: dict[str, float] = {}

        # Generate 1981-2023 monthly data, with 2022.07 and 2023.12 omitted
        for year in range(1981, 2024):
            for month in range(1, 13):
                key = f"{year:04d}.{month:02d}"
                if month in (11, 12, 1, 2, 3, 4):
                    rain_val = float(rng.gamma(shape=4.0, scale=28.0))
                else:
                    rain_val = float(rng.gamma(shape=0.8, scale=4.0))
                monthly_rain[key] = rain_val
                monthly_temp[key] = 23.0 + float(rng.normal(0.0, 0.5))

        del monthly_rain["2022.07"]
        del monthly_rain["2023.12"]

        summary = build_unit_climate_summary(
            unit_id="test-unit",
            name="Test Unit",
            country="ZW",
            role="treated",
            eligible=True,
            chirps_pixel_count=100,
            monthly_precip_mm=monthly_rain,
            monthly_t2m_c=monthly_temp,
            years=tuple(range(1981, 2024)),
            baseline_period=(1981, 2010),
        )

        rec_by_year = summary.record_by_year()
        rec_2021 = rec_by_year[2021]
        rec_2022 = rec_by_year[2022]
        rec_2023 = rec_by_year[2023]
        assert rec_2021.is_complete_year is True
        assert rec_2021.annual_rainfall_mm is not None
        assert rec_2021.spi_12 is not None

        # 2022 is missing July (month 7): annual total and SPI-12 must be None,
        # while partial_year_rainfall_mm and wet_season_rainfall_mm (Nov 2021 - Apr 2022) are preserved!
        assert rec_2022.is_complete_year is False
        assert rec_2022.valid_months == 11
        assert rec_2022.missing_months == (7,)
        assert rec_2022.annual_rainfall_mm is None
        assert rec_2022.rainfall_anomaly_mm is None
        assert rec_2022.spi_12 is None
        assert rec_2022.partial_year_rainfall_mm is not None
        assert rec_2022.wet_season_rainfall_mm is not None
        assert rec_2022.spi_6_wet is not None

        # 2023 is missing Dec (month 12): annual total and SPI-12 must be None,
        # while Nov 2022 - Apr 2023 wet season is 100% complete!
        assert rec_2023.is_complete_year is False
        assert rec_2023.valid_months == 11
        assert rec_2023.missing_months == (12,)
        assert rec_2023.annual_rainfall_mm is None
        assert rec_2023.spi_12 is None
        assert rec_2023.wet_season_rainfall_mm is not None
        assert rec_2023.spi_6_wet is not None

    def test_missing_wet_season_month_withholds_wet_season_and_spi6(self) -> None:
        rng = np.random.default_rng(99)
        monthly_rain: dict[str, float] = {}
        for year in range(1981, 2015):
            for month in range(1, 13):
                monthly_rain[f"{year:04d}.{month:02d}"] = float(rng.gamma(3.0, 20.0))

        # Knock out Jan 2012 (which belongs to the 2012 Austral wet season Nov 2011 - Apr 2012)
        del monthly_rain["2012.01"]

        summary = build_unit_climate_summary(
            unit_id="test-wet-gap",
            name="Test Wet Gap",
            country="ZW",
            role="donor",
            eligible=True,
            chirps_pixel_count=50,
            monthly_precip_mm=monthly_rain,
            years=tuple(range(1981, 2015)),
        )
        rec_2012 = summary.record_by_year()[2012]
        assert rec_2012.is_complete_year is False
        assert rec_2012.wet_season_rainfall_mm is None
        assert rec_2012.spi_6_wet is None
        assert rec_2012.spi_3_peak is None

    def test_spi_refuses_insufficient_baseline_years(self) -> None:
        # Only 12 valid baseline years (< min_baseline_years = 20)
        values = [650.0 + (i % 5) * 30.0 for i in range(12)]
        mask = [True for _ in range(12)]
        spi = compute_gamma_spi(values, mask, min_baseline_years=20)
        assert all(val is None for val in spi)


# ============================================================================
# 3. TEMPORAL ALIGNMENT
# ============================================================================


class TestTemporalAlignment:
    """Verify alignment between satellite observation periods and climate series."""

    def test_alignment_with_kariba_panel_window_2001_2022(self) -> None:
        bundle = load_kariba_climate_bundle(DEFAULT_CLIMATE_CACHE_PATH)
        kariba_climate = bundle.treated_summary
        satellite_years = list(range(2001, 2023))  # 22 years (2001-2022)
        satellite_values = [0.50 for _ in satellite_years]

        report = align_climate_to_satellite_years(
            climate_summary=kariba_climate,
            satellite_years=satellite_years,
            satellite_values=satellite_values,
            satellite_indicator="NDVI",
        )

        assert report.unit_id == "kariba-redd"
        assert len(report.satellite_years) == 22
        assert len(report.aligned_years) == 22
        assert report.missing_climate_years == ()
        assert report.incomplete_climate_years == (2022,)
        assert report.chirts_uncovered_years == (2017, 2018, 2019, 2020, 2021, 2022)
        assert report.interpolation_applied is False
        assert report.alignment_status == "PARTIAL"
        assert len(report.notes) >= 3

    def test_alignment_with_sentinel2_window_2021_2023(self) -> None:
        bundle = load_kariba_climate_bundle(DEFAULT_CLIMATE_CACHE_PATH)
        kariba_climate = bundle.treated_summary

        report = align_climate_to_satellite_years(
            climate_summary=kariba_climate,
            satellite_years=[2021, 2022, 2023],
            satellite_values=[0.4255, 0.4206, 0.3450],
            satellite_indicator="NDVI",
        )

        assert report.satellite_years == (2021, 2022, 2023)
        assert report.incomplete_climate_years == (2022, 2023)
        assert report.chirts_uncovered_years == (2021, 2022, 2023)
        assert report.interpolation_applied is False

        obs_by_year = {obs.year: obs for obs in report.aligned_records}
        assert obs_by_year[2021].annual_rainfall_mm is not None
        assert obs_by_year[2022].annual_rainfall_mm is None
        assert obs_by_year[2022].wet_season_rainfall_mm is not None
        assert obs_by_year[2023].annual_rainfall_mm is None
        assert obs_by_year[2023].wet_season_rainfall_mm is not None
        assert obs_by_year[2023].mean_temp_c is not None

    def test_strict_complete_calendar_years_raises_on_partial_year(self) -> None:
        bundle = load_kariba_climate_bundle(DEFAULT_CLIMATE_CACHE_PATH)
        kariba_climate = bundle.treated_summary

        with pytest.raises(DataUnavailableError, match="incomplete climate coverage"):
            align_climate_to_satellite_years(
                climate_summary=kariba_climate,
                satellite_years=[2021, 2022, 2023],
                satellite_values=[0.4255, 0.4206, 0.3450],
                require_complete_climate_years=True,
            )


# ============================================================================
# 4. REAL KARIBA CHIRPS & NASA POWER BUNDLE + SPI DROUGHT VERIFICATION
# ============================================================================


class TestKaribaClimateBundleAndSPI:
    """Verify real CHIRPS v2.0 + NASA POWER MERRA-2 bundle integrity and SPI drought indices."""

    def test_kariba_climate_bundle_provenance_and_spatial_coverage(self) -> None:
        bundle = load_kariba_climate_bundle(DEFAULT_CLIMATE_CACHE_PATH)

        # Provenance checks
        assert "chirps_v2_monthly" in bundle.sources
        chirps_prov = bundle.sources["chirps_v2_monthly"]
        assert chirps_prov.resolution_deg == pytest.approx(0.05)
        assert chirps_prov.canonical_unit == "mm/year"
        assert chirps_prov.temporal_coverage_start == "1981-01"
        assert chirps_prov.temporal_coverage_end == "2023-12"
        assert len(bundle.sha256) == 64

        assert "nasa_power_merra2_monthly" in bundle.sources
        temp_prov = bundle.sources["nasa_power_merra2_monthly"]
        assert temp_prov.canonical_unit == "degC"
        assert temp_prov.known_coverage_gaps == ()

        assert "chirts_max_cdr_reference" in bundle.sources
        chirts_prov = bundle.sources["chirts_max_cdr_reference"]
        assert chirts_prov.temporal_coverage_end == "2016-12"

        # Spatial coverage checks: Kariba AOI + all 50 ADM2 districts (including all 37 eligible donors)
        assert "kariba-redd" in bundle.unit_summaries
        assert len(bundle.unit_summaries) == 51
        kariba = bundle.treated_summary
        assert kariba.chirps_pixel_count == 515

        donor_summaries = bundle.eligible_donor_summaries()
        assert len(donor_summaries) == 37
        for _did, u in donor_summaries.items():
            assert u.chirps_pixel_count > 0
            assert 400.0 <= u.baseline_mean_rainfall_mm <= 1500.0
            assert 15.0 <= (u.baseline_mean_temp_c or 0.0) <= 30.0

    def test_kariba_historical_droughts_detected_by_spi(self) -> None:
        bundle = load_kariba_climate_bundle(DEFAULT_CLIMATE_CACHE_PATH)
        kariba_by_year = bundle.treated_summary.record_by_year()

        # 2002 El Nino / Southern African drought (pre-treatment)
        r2002 = kariba_by_year[2002]
        assert r2002.annual_rainfall_mm is not None and r2002.annual_rainfall_mm < 500.0
        assert r2002.spi_12 is not None and r2002.spi_12 <= -1.5
        assert r2002.drought_classification in ("severe_drought", "extreme_drought")

        # 2019 Southern African drought (post-treatment)
        r2019 = kariba_by_year[2019]
        assert r2019.annual_rainfall_mm is not None and r2019.annual_rainfall_mm < 500.0
        assert r2019.spi_12 is not None and r2019.spi_12 <= -1.5
        assert r2019.drought_classification in ("severe_drought", "extreme_drought")

        # 2001 wet year (pre-treatment)
        r2001 = kariba_by_year[2001]
        assert r2001.annual_rainfall_mm is not None and r2001.annual_rainfall_mm > 880.0
        assert r2001.spi_12 is not None and r2001.spi_12 > 1.0
        assert classify_spi_drought(r2001.spi_12) in ("moderately_wet", "very_wet", "extremely_wet")


# ============================================================================
# 5. DONOR CLIMATE COMPARABILITY & CONFOUNDING DIAGNOSTICS
# ============================================================================


class TestDonorClimateComparabilityAndConfounding:
    """Verify donor climate comparability evaluation and weather-confounding adjustment."""

    def test_donor_climate_comparability_flags_extreme_wet_and_cool_donors(self) -> None:
        bundle = load_kariba_climate_bundle(DEFAULT_CLIMATE_CACHE_PATH)
        donor_list = list(bundle.eligible_donor_summaries().values())

        diag = evaluate_donor_climate_comparability(
            treated_summary=bundle.treated_summary,
            donor_summaries=donor_list,
            pre_years=tuple(range(2001, 2011)),
            post_years=tuple(range(2011, 2023)),
        )

        assert diag.donor_count == 37
        assert diag.comparable_donor_count == 30
        flagged_ids = [c.donor_id for c in diag.donor_comparability if not c.is_climate_comparable]
        assert len(flagged_ids) == 7
        # High-rainfall northern Central Province Zambia districts (>1000 mm/yr vs 733 mm/yr at Kariba)
        assert "zm-chitambo" in flagged_ids
        assert "zm-serenje" in flagged_ids
        assert "zm-mkushi" in flagged_ids
        # Cooler high-elevation Mashonaland East districts (~19.2 degC vs 23.3 degC at Kariba)
        assert "zw-chikomba" in flagged_ids
        assert "zw-seke" in flagged_ids

        # Climate SMD balance must fail the 0.25 threshold because Kariba is hotter and drier than average donor
        assert diag.climate_covariate_balance_unweighted.is_balanced is False
        assert diag.climate_covariate_balance_unweighted.max_abs_smd > 0.25

    def test_post_treatment_covariate_divergence_warning(self) -> None:
        bundle = load_kariba_climate_bundle(DEFAULT_CLIMATE_CACHE_PATH)
        donor_list = list(bundle.eligible_donor_summaries().values())
        cov_names = ("wet_season_rainfall_mm", "spi_12", "mean_temp_c")
        all_years = list(range(2001, 2023))

        t_X, d_X = build_climate_covariate_matrices(
            bundle.treated_summary, donor_list, all_years, cov_names
        )
        warn_msg = check_post_treatment_covariate_divergence(
            t_X[:10, :],
            t_X[10:, :],
            d_X[:10, :, :],
            d_X[10:, :, :],
            cov_names,
        )
        assert warn_msg is not None
        assert "exogeneity" in warn_msg.lower()

    def test_climate_residualization_recovers_true_effect_under_synthetic_weather_shock(
        self,
    ) -> None:
        """When an exogenous post-treatment drought depresses only the treated unit's
        vegetation while the true treatment effect is zero, unadjusted SCM/DiD mistakes
        the drought for a negative treatment effect, whereas climate-adjusted SCM/DiD
        removes the weather shock without modifying fit_synthetic_control or estimate_did.
        """
        rng = np.random.default_rng(2026)
        pre_years = tuple(range(2001, 2011))
        post_years = tuple(range(2011, 2021))
        all_years = pre_years + post_years
        donor_ids = [f"donor-{i}" for i in range(6)]

        # Create synthetic climate summaries for treated + 6 donors
        unit_climates = {}
        for uid in ["treated", *donor_ids]:
            monthly_rain: dict[str, float] = {}
            monthly_temp: dict[str, float] = {}
            for y in range(1981, 2021):
                # In 2015-2019, give 'treated' a severe exogenous rainfall deficit
                is_treated_drought = (uid == "treated") and (2015 <= y <= 2019)
                for m in range(1, 13):
                    base_m = 95.0 if m in (11, 12, 1, 2, 3, 4) else 5.0
                    if is_treated_drought and m in (11, 12, 1, 2, 3, 4):
                        base_m -= 40.0
                    noise = float(rng.normal(0.0, 6.0))
                    monthly_rain[f"{y:04d}.{m:02d}"] = max(1.0, base_m + noise)
                    monthly_temp[f"{y:04d}.{m:02d}"] = 23.0 + float(rng.normal(0.0, 0.2))
            unit_climates[uid] = build_unit_climate_summary(
                unit_id=uid,
                name=uid,
                country="ZW",
                role="treated" if uid == "treated" else "donor",
                eligible=True,
                chirps_pixel_count=50,
                monthly_precip_mm=monthly_rain,
                monthly_t2m_c=monthly_temp,
                years=tuple(range(1981, 2021)),
                post_treatment_period=(2011, 2020),
            )

        # True vegetation outcome: baseline 0.50 + 0.0003 * (wet_season_rainfall - 600) + small noise
        # True causal treatment effect = 0.0!
        true_beta = 0.0003
        donor_cols: list[np.ndarray] = []
        for did in donor_ids:
            rec_map = unit_climates[did].record_by_year()
            wet_vec = np.array(
                [rec_map[y].wet_season_rainfall_mm for y in all_years],
                dtype=np.float64,
            )
            donor_cols.append(
                0.50 + true_beta * (wet_vec - 600.0) + rng.normal(0.0, 0.001, len(all_years))
            )
        donor_Y = np.column_stack(donor_cols)

        t_rec_map = unit_climates["treated"].record_by_year()
        treated_wet = np.array(
            [t_rec_map[y].wet_season_rainfall_mm for y in all_years],
            dtype=np.float64,
        )
        treated_Y = (
            0.50 + true_beta * (treated_wet - 600.0) + rng.normal(0.0, 0.001, len(all_years))
        )

        report = run_climate_confounding_analysis(
            case_id="synthetic-weather-shock-test",
            treated_pre=treated_Y[:10],
            donor_pre=donor_Y[:10, :],
            treated_post=treated_Y[10:],
            donor_post=donor_Y[10:, :],
            donor_ids=donor_ids,
            treated_climate=unit_climates["treated"],
            donor_climates=[unit_climates[did] for did in donor_ids],
            pre_years=pre_years,
            post_years=post_years,
        )

        unadj = report.unadjusted_spec
        wet_spec = next(
            s for s in report.sensitivity_specs if s.spec_name == "chirps_wet_season_rainfall"
        )

        # Unadjusted SCM and DiD are confounded by the treated unit's post-treatment drought (~ -0.036 NDVI)
        assert unadj.scm_fit.average_effect < -0.025
        assert unadj.did_result.estimate < -0.025

        # Climate-adjusted SCM and DiD recover the true zero treatment effect within ~0.003 NDVI!
        assert abs(wet_spec.scm_fit.average_effect) < 0.003
        assert abs(wet_spec.did_result.estimate) < 0.003


# ============================================================================
# 6. CAUSAL IDENTIFICATION GATE PRESERVATION & SCIENTIFIC INTEGRITY
# ============================================================================


class TestCausalGatePreservation:
    """Verify that adding climate covariates never weakens or bypasses causal identification gates."""

    def test_existing_scm_and_did_estimators_unchanged(self) -> None:
        scm_sig = inspect.signature(fit_synthetic_control)
        did_sig = inspect.signature(estimate_did)
        assert list(scm_sig.parameters.keys()) == [
            "treated_series",
            "donor_matrix",
            "donor_ids",
            "n_pre_periods",
            "ridge",
            "min_pre_periods",
        ]
        assert list(did_sig.parameters.keys()) == [
            "treated_series",
            "control_matrix",
            "n_pre_periods",
            "min_pre_periods",
            "clusters",
            "cluster_level",
            "seed",
            "n_bootstrap",
        ]

    def test_all_10_kariba_specifications_preserve_inconclusive_verdict(self) -> None:
        bundle = load_kariba_climate_bundle(DEFAULT_CLIMATE_CACHE_PATH)
        donor_ids = list(bundle.eligible_donor_ids)
        donor_climates = [bundle.unit_summaries[did] for did in donor_ids]

        # Run on Kariba benchmark fixture panel (2001-2022, J=37 > T0=10)
        obs_port = SyntheticFixtureObservationAccess()
        pre_years = tuple(range(2001, 2011))
        post_years = tuple(range(2011, 2023))

        series_map = {
            uid: obs_port.series(
                ObservationSpec(
                    unit=UnitRef(unit_id=uid),
                    indicator=Indicator.NDVI,
                    start_period=2001,
                    end_period=2022,
                )
            )
            for uid in ["kariba-redd", *donor_ids]
        }

        t_ts = dict(
            zip(series_map["kariba-redd"].periods, series_map["kariba-redd"].values, strict=True)
        )
        t_pre = np.array([t_ts[y] for y in pre_years], dtype=np.float64)
        t_post = np.array([t_ts[y] for y in post_years], dtype=np.float64)

        d_pre_cols = []
        d_post_cols = []
        for uid in donor_ids:
            d_ts = dict(zip(series_map[uid].periods, series_map[uid].values, strict=True))
            d_pre_cols.append(np.array([d_ts[y] for y in pre_years], dtype=np.float64))
            d_post_cols.append(np.array([d_ts[y] for y in post_years], dtype=np.float64))
        d_pre = np.column_stack(d_pre_cols)
        d_post = np.column_stack(d_post_cols)

        report = run_climate_confounding_analysis(
            case_id="kariba-redd-fixture",
            treated_pre=t_pre,
            donor_pre=d_pre,
            treated_post=t_post,
            donor_post=d_post,
            donor_ids=donor_ids,
            treated_climate=bundle.treated_summary,
            donor_climates=donor_climates,
            pre_years=pre_years,
            post_years=post_years,
        )

        assert report.causal_gates_preserved is True
        assert report.final_verdict == VerdictLabel.INCONCLUSIVE
        assert report.unadjusted_spec.verdict_after_gates == VerdictLabel.INCONCLUSIVE
        assert len(report.sensitivity_specs) == 10
        for spec in report.sensitivity_specs:
            assert spec.verdict_after_gates == VerdictLabel.INCONCLUSIVE
            assert spec.identifiability_preserved is True
            assert any("under_identified_simplex" in r for r in spec.gate_failure_reasons)

    def test_gate_evaluator_rejects_even_if_fit_and_weights_pass_when_j_exceeds_t0(self) -> None:
        # Construct a synthetic fit with low pre_rmspe and sparse weights, but J=37 > T_0=10
        w = np.zeros(37, dtype=np.float64)
        w[0] = 0.6
        w[1] = 0.4
        fake_fit = SyntheticControlFit(
            weights=w,
            donor_ids=tuple(f"d-{i}" for i in range(37)),
            pre_rmspe=0.0005,
            post_rmspe=0.020,
            treated_pre=np.full(10, 0.50),
            synthetic_pre=np.full(10, 0.50),
            treated_post=np.full(12, 0.52),
            synthetic_post=np.full(12, 0.50),
            n_iterations=10,
            converged=True,
            n_pre_periods=10,
            hull=None,
        )
        verdict, reasons = evaluate_causal_gates_for_spec(
            fake_fit,
            donor_count=37,
            pre_periods=10,
            biomass_calibrated=True,
        )
        assert verdict == VerdictLabel.INCONCLUSIVE
        assert any("under_identified_simplex" in r for r in reasons)

    def test_sentinel2_comovement_explicitly_refuses_causal_identification(self) -> None:
        bundle = load_kariba_climate_bundle(DEFAULT_CLIMATE_CACHE_PATH)
        s2_comovement = analyze_sentinel2_climate_comovement(
            climate_summary=bundle.treated_summary,
            years=(2021, 2022, 2023),
            ndvi_values=(0.425465, 0.420619, 0.344995),
            evi_values=(0.243256, 0.231527, 0.198776),
            ndmi_values=(-0.069341, -0.089639, -0.109568),
            nbr_values=(0.137656, 0.117227, 0.089675),
        )

        assert s2_comovement.identifies_causal_effect is False
        assert s2_comovement.ndvi_2023_vs_2021_2022_delta == pytest.approx(-0.0780, abs=1e-4)
        assert s2_comovement.ndmi_2023_vs_2021_2022_delta == pytest.approx(-0.0301, abs=1e-4)
        assert s2_comovement.ndmi_values == (-0.069341, -0.089639, -0.109568)
        assert s2_comovement.temp_2023_vs_2021_2022_delta_c is not None
        assert s2_comovement.temp_2023_vs_2021_2022_delta_c > 1.0  # +1.124 degC warmer in 2023
        assert any(
            "does not establish causality" in n.lower() for n in s2_comovement.interpretation_notes
        )


# ============================================================================
# 7. REGRESSION TESTS: SENTINEL-2 NDMI INTEGRITY & CACHE CONSISTENCY (TASK 3C)
# ============================================================================


class TestSentinel2NDMIIntegrity:
    """Verify Sentinel-2 NDMI calculation, sign convention, and pipeline integration."""

    def test_stac_cache_ndmi_values_and_provenance(self) -> None:
        import json
        from pathlib import Path

        ndmi_cache_path = (
            Path(__file__).resolve().parents[2]
            / "data"
            / "processed"
            / "stac_cache"
            / "kariba-redd__ndmi.json"
        )
        assert ndmi_cache_path.exists(), f"NDMI cache missing at {ndmi_cache_path}"
        data = json.loads(ndmi_cache_path.read_text(encoding="utf-8"))

        records = data["records"]
        assert len(records) == 3
        r_map = {r["year"]: r["value"] for r in records}

        # Exact recorded values in STAC cache
        assert r_map[2021] == pytest.approx(-0.06934131931717002, abs=1e-6)
        assert r_map[2022] == pytest.approx(-0.0896392525162966, abs=1e-6)
        assert r_map[2023] == pytest.approx(-0.10956805847608864, abs=1e-6)

        # All values must be strictly negative during the June dry season in Kariba
        assert all(val < 0.0 for val in r_map.values())
        # Monotonic drying trajectory from 2021 to 2023
        assert r_map[2021] > r_map[2022] > r_map[2023]

    def test_ndmi_formula_and_sign_convention(self) -> None:
        from groundtruth.engine.observation.indices import ndmi

        # In dense green foliage with high leaf moisture: NIR (0.40) > SWIR1 (0.20) -> NDMI > 0
        moist_nir = np.array([0.40])
        moist_swir1 = np.array([0.20])
        res_moist = ndmi(moist_nir, moist_swir1)
        assert res_moist[0] == pytest.approx((0.40 - 0.20) / (0.40 + 0.20), abs=1e-6)
        assert res_moist[0] > 0.0

        # In dry savanna / senescent woodland (Kariba June dry season): NIR (0.22) < SWIR1 (0.26) -> NDMI < 0
        dry_nir = np.array([0.22])
        dry_swir1 = np.array([0.26])
        res_dry = ndmi(dry_nir, dry_swir1)
        assert res_dry[0] == pytest.approx((0.22 - 0.26) / (0.22 + 0.26), abs=1e-6)
        assert res_dry[0] < 0.0

    def test_missing_observations_remain_none_without_default_fabrication(self) -> None:
        bundle = load_kariba_climate_bundle(DEFAULT_CLIMATE_CACHE_PATH)
        # Call without providing spectral values
        res = analyze_sentinel2_climate_comovement(
            climate_summary=bundle.treated_summary,
            years=(2021, 2022, 2023),
        )
        assert res.ndvi_values == (None, None, None)
        assert res.ndmi_values == (None, None, None)
        assert res.evi_values == (None, None, None)
        assert res.nbr_values == (None, None, None)
        assert res.ndvi_2023_vs_2021_2022_delta is None
        assert res.ndmi_2023_vs_2021_2022_delta is None
        assert any("unavailable or incomplete" in n for n in res.interpretation_notes)
        assert res.identifies_causal_effect is False

    def test_scm_and_did_unaffected_by_ndmi_correction(self) -> None:
        # Verify that causal estimation operates strictly on NDVI and does not change
        bundle = load_kariba_climate_bundle(DEFAULT_CLIMATE_CACHE_PATH)
        donor_ids = list(bundle.eligible_donor_ids)
        obs_port = SyntheticFixtureObservationAccess()
        pre_years = tuple(range(2001, 2011))
        post_years = tuple(range(2011, 2023))

        s_kariba = obs_port.series(
            ObservationSpec(
                unit=UnitRef(unit_id="kariba-redd"),
                indicator=Indicator.NDVI,
                start_period=2001,
                end_period=2022,
            )
        )
        t_ts = dict(zip(s_kariba.periods, s_kariba.values, strict=True))
        t_pre = np.array([t_ts[y] for y in pre_years], dtype=np.float64)
        t_post = np.array([t_ts[y] for y in post_years], dtype=np.float64)

        d_pre_cols = []
        d_post_cols = []
        for uid in donor_ids:
            d_ts = dict(
                zip(
                    obs_port.series(
                        ObservationSpec(
                            unit=UnitRef(unit_id=uid),
                            indicator=Indicator.NDVI,
                            start_period=2001,
                            end_period=2022,
                        )
                    ).periods,
                    obs_port.series(
                        ObservationSpec(
                            unit=UnitRef(unit_id=uid),
                            indicator=Indicator.NDVI,
                            start_period=2001,
                            end_period=2022,
                        )
                    ).values,
                    strict=True,
                )
            )
            d_pre_cols.append([d_ts[y] for y in pre_years])
            d_post_cols.append([d_ts[y] for y in post_years])

        report = run_climate_confounding_analysis(
            case_id="kariba-redd-test",
            treated_pre=t_pre,
            donor_pre=np.column_stack(d_pre_cols),
            treated_post=t_post,
            donor_post=np.column_stack(d_post_cols),
            donor_ids=donor_ids,
            treated_climate=bundle.treated_summary,
            donor_climates=[bundle.unit_summaries[did] for did in donor_ids],
            pre_years=pre_years,
            post_years=post_years,
        )

        assert report.unadjusted_spec.scm_fit.pre_rmspe == pytest.approx(0.001382, abs=1e-5)
        assert report.unadjusted_spec.scm_fit.average_effect == pytest.approx(0.041580, abs=1e-5)
        assert report.unadjusted_spec.did_result.estimate == pytest.approx(0.041561, abs=1e-5)
        assert report.final_verdict == VerdictLabel.INCONCLUSIVE
