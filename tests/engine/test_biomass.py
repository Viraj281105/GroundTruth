"""Unit tests for the biomass -> carbon conversion layer.

GroundTruth enforces 'NDVI is not carbon'. The conversion needs an explicit,
sourced, site-calibrated biomass model; none is shipped by default. All
calibrations below are **TEST-ONLY synthetic values** (``calibration_is_test_fixture``)
that exercise the arithmetic. They are not field-derived and no result computed
from them is a real-world finding.
"""

from __future__ import annotations

from typing import Any

import pytest

from groundtruth.contracts.types import Confidence, VerdictLabel
from groundtruth.contracts.units import assert_not_index_to_carbon, unit_family
from groundtruth.engine.assembler import AssemblyInputs, assemble_evidence
from groundtruth.engine.biomass import (
    DEFAULT_BIOMASS_PARAMETERS,
    BiomassParameters,
    CarbonEstimate,
    ClaimComparison,
    NotCalibratedError,
    benchmark_against_claim,
    convert_agb_to_carbon,
    convert_indicator_to_carbon,
    get_biomass_parameters,
)
from groundtruth.engine.biomass.allometry import ASSUMED_ONE_SIGMA_KIND, ONE_SIGMA_LEVEL


def make_test_calibration(**kw: float) -> BiomassParameters:
    """TEST-ONLY calibration. Values are arbitrary and have no field basis."""
    base: dict[str, object] = {
        "region_type": "test-only",
        "ndvi_to_agb_slope": 100.0,
        "root_to_shoot_ratio": 0.25,
        "allometry_relative_error": 0.20,
        "calibration_source": "TEST-ONLY synthetic values; not field-derived",
        "calibration_is_test_fixture": True,
    }
    base.update(kw)
    return BiomassParameters(**base)  # type: ignore[arg-type]


class TestNoDefaultCalibration:
    def test_default_parameters_are_uncalibrated(self) -> None:
        params = BiomassParameters()
        assert params.ndvi_to_agb_slope is None
        assert params.root_to_shoot_ratio is None
        assert params.allometry_relative_error is None
        assert params.is_calibrated is False
        assert "calibration_source" in params.missing_calibration()

    def test_generic_constants_only(self) -> None:
        params = BiomassParameters()
        assert params.cf == pytest.approx(0.47)
        assert params.co2_to_c_ratio == pytest.approx(44.0 / 12.0)

    def test_regional_templates_ship_no_slopes(self) -> None:
        assert {"miombo", "tropical_dry_forest", "mangrove", "moist_tropical"} <= set(
            DEFAULT_BIOMASS_PARAMETERS
        )
        for name, tmpl in DEFAULT_BIOMASS_PARAMETERS.items():
            assert tmpl.ndvi_to_agb_slope is None, name
            assert tmpl.is_calibrated is False, name
        assert get_biomass_parameters("miombo").is_calibrated is False

    def test_slope_without_source_is_not_calibrated(self) -> None:
        params = BiomassParameters(
            ndvi_to_agb_slope=100.0, root_to_shoot_ratio=0.25, allometry_relative_error=0.2
        )
        assert params.is_calibrated is False
        assert params.missing_calibration() == ["calibration_source"]

    def test_conversion_refuses_without_calibration(self) -> None:
        with pytest.raises(NotCalibratedError, match="NOT CALIBRATED"):
            convert_indicator_to_carbon(0.05, 10_000.0, get_biomass_parameters("miombo"))

    def test_overrides_with_full_calibration_work(self) -> None:
        custom = get_biomass_parameters(
            "miombo",
            ndvi_to_agb_slope=125.0,
            root_to_shoot_ratio=0.3,
            allometry_relative_error=0.2,
            calibration_source="TEST-ONLY",
            calibration_is_test_fixture=True,
        )
        assert custom.is_calibrated
        assert custom.region_type == "miombo"

    def test_invalid_parameters_raise(self) -> None:
        with pytest.raises(ValueError):
            BiomassParameters(cf=1.5)
        with pytest.raises(ValueError):
            BiomassParameters(ndvi_to_agb_slope=-10.0)


class TestIndicatorToCarbonConversion:
    def test_conversion_math_keeps_quantities_distinct(self) -> None:
        params = make_test_calibration(cf=0.50)
        estimate = convert_indicator_to_carbon(0.05, 10_000.0, params)
        assert isinstance(estimate, CarbonEstimate)
        assert estimate.delta_agb_t_per_ha == pytest.approx(5.0)
        assert estimate.delta_total_biomass_t_per_ha == pytest.approx(6.25)
        assert estimate.delta_carbon_t_per_ha == pytest.approx(3.125)
        assert estimate.delta_tco2e_per_ha == pytest.approx(3.125 * 44.0 / 12.0)
        assert estimate.cumulative_tco2e == pytest.approx(3.125 * 44.0 / 12.0 * 10_000.0)

    def test_interval_is_one_sigma_not_95(self) -> None:
        estimate = convert_indicator_to_carbon(
            0.04, 50_000.0, make_test_calibration(allometry_relative_error=0.25)
        )
        assert estimate.std_error_tco2e == pytest.approx(estimate.cumulative_tco2e * 0.25)
        assert estimate.uncertainty_lower_tco2e == pytest.approx(estimate.cumulative_tco2e * 0.75)
        assert estimate.uncertainty_upper_tco2e == pytest.approx(estimate.cumulative_tco2e * 1.25)

        envelope = estimate.envelope()
        assert envelope.kind == ASSUMED_ONE_SIGMA_KIND
        assert envelope.level == pytest.approx(ONE_SIGMA_LEVEL)
        assert envelope.level != pytest.approx(0.95)

    def test_indicator_uncertainty_combines_in_quadrature(self) -> None:
        estimate = convert_indicator_to_carbon(
            0.05,
            10_000.0,
            make_test_calibration(allometry_relative_error=0.25),
            indicator_std_error=0.01,
        )
        rel = (0.25**2 + 0.20**2) ** 0.5
        assert estimate.std_error_tco2e == pytest.approx(estimate.cumulative_tco2e * rel)

    def test_negative_indicator_delta_bounds_ordered(self) -> None:
        estimate = convert_indicator_to_carbon(-0.02, 10_000.0, make_test_calibration())
        assert estimate.cumulative_tco2e < 0.0
        assert estimate.uncertainty_lower_tco2e <= estimate.uncertainty_upper_tco2e

    def test_invalid_area_raises(self) -> None:
        with pytest.raises(ValueError, match="area_ha must be positive"):
            convert_indicator_to_carbon(0.05, 0.0, make_test_calibration())


class TestIndexToCarbonGuard:
    def test_direct_index_to_carbon_conversion_fails(self) -> None:
        with pytest.raises(ValueError, match="is not a carbon stock"):
            assert_not_index_to_carbon("ndvi", "tCO2e")
        with pytest.raises(ValueError, match="is not a carbon stock"):
            assert_not_index_to_carbon("evi", "tC")

    def test_share_is_registered_in_unit_families(self) -> None:
        from groundtruth.contracts.units import UnitFamily

        assert unit_family("share") is UnitFamily.FRACTION


class TestClaimBenchmarkArithmetic:
    """Arithmetic of the claim comparison on ARBITRARY numbers (no real project)."""

    def test_divergent_claim(self) -> None:
        comparison = benchmark_against_claim(
            claimed_tco2e=1_000_000.0,
            estimated_tco2e=400_000.0,
            lower_tco2e=300_000.0,
            upper_tco2e=500_000.0,
        )
        assert isinstance(comparison, ClaimComparison)
        assert comparison.over_issuance_share == pytest.approx(0.60)
        assert comparison.over_issuance_range == (pytest.approx(0.5), pytest.approx(0.7))
        assert comparison.divergence_ratio == pytest.approx(0.4)
        assert comparison.verdict_label is VerdictLabel.DIVERGENT_FROM_CLAIM

        env = comparison.envelope()
        assert isinstance(env, Confidence)
        assert env.kind == ASSUMED_ONE_SIGMA_KIND
        assert env.level == pytest.approx(ONE_SIGMA_LEVEL)

    def test_consistent_claim(self) -> None:
        comparison = benchmark_against_claim(10_000_000.0, 9_500_000.0, 7_000_000.0, 12_000_000.0)
        assert comparison.over_issuance_share == pytest.approx(0.05)
        assert comparison.verdict_label is VerdictLabel.CONSISTENT_WITH_CLAIM

    def test_invalid_claim_arguments_raise(self) -> None:
        with pytest.raises(ValueError, match="claimed_tco2e must be positive"):
            benchmark_against_claim(0.0, 100.0, 50.0, 150.0)
        with pytest.raises(ValueError, match="cannot exceed upper_tco2e"):
            benchmark_against_claim(100.0, 50.0, 150.0, 50.0)


def _with_claim(inputs: AssemblyInputs, params: BiomassParameters | None) -> AssemblyInputs:
    request = inputs.request.model_copy(
        update={
            "project": inputs.request.project.model_copy(update={"area_ha": 50_000.0}),
            "claim": inputs.request.claim.model_copy(
                update={"claimed_credits_tco2e": 5_000_000.0, "project_area_ha": 50_000.0}
            ),
        }
    )
    return AssemblyInputs(
        request=request,
        indicator_unit=inputs.indicator_unit,
        donor_pool=inputs.donor_pool,
        fit=inputs.fit,
        panel=inputs.panel,
        placebo=inputs.placebo,
        in_time_placebo=inputs.in_time_placebo,
        leave_one_out=inputs.leave_one_out,
        specification_curve=inputs.specification_curve,
        did=inputs.did,
        data_provenance=inputs.data_provenance,
        notices=inputs.notices,
        biomass_params=params,
    )


class TestAssemblerIntegration:
    def test_calibrated_params_produce_labelled_carbon_evidence(
        self, assembly_inputs: Any, factor_panel: Any
    ) -> None:
        outcomes, unit_ids, n_pre, _ = factor_panel
        inputs = _with_claim(assembly_inputs(outcomes, unit_ids, n_pre), make_test_calibration())
        bundle = assemble_evidence(inputs)

        est = bundle.require("carbon.estimated_tco2e")
        assert est.unit == "tCO2e"
        assert est.confidence is not None
        assert est.confidence.kind == ASSUMED_ONE_SIGMA_KIND
        assert est.confidence.level == pytest.approx(ONE_SIGMA_LEVEL)
        assert est.qualifiers["calibration_is_test_fixture"] is True
        assert est.qualifiers["calibration_source"].startswith("TEST-ONLY")
        assert est.provenance.parameters["ndvi_to_agb_slope"] == pytest.approx(100.0)

        share = bundle.require("carbon.over_issuance_share")
        assert share.confidence is not None
        assert share.confidence.level != pytest.approx(0.95)

        assert bundle.verdict is not None
        joined = " ".join(bundle.verdict.caveats)
        assert "not a 95% confidence interval" in joined
        assert "not validated against field plots" in joined or "has not validated" in joined

    def test_uncalibrated_params_yield_inconclusive_not_calibrated(
        self, assembly_inputs: Any, factor_panel: Any
    ) -> None:
        outcomes, unit_ids, n_pre, _ = factor_panel
        inputs = _with_claim(
            assembly_inputs(outcomes, unit_ids, n_pre), get_biomass_parameters("miombo")
        )
        bundle = assemble_evidence(inputs)

        assert "carbon.estimated_tco2e" not in bundle
        assert "carbon.over_issuance_share" not in bundle
        assert bundle.verdict is not None
        assert bundle.verdict.label is VerdictLabel.INCONCLUSIVE
        assert bundle.verdict.divergence_ratio is None
        assert any("NOT CALIBRATED" in w for w in bundle.warnings)

    def test_without_biomass_params_remains_inconclusive(
        self, assembly_inputs: Any, factor_panel: Any
    ) -> None:
        outcomes, unit_ids, n_pre, _ = factor_panel
        bundle = assemble_evidence(
            assembly_inputs(outcomes, unit_ids, n_pre), divergence_ratio=None
        )
        assert bundle.verdict is not None
        assert bundle.verdict.label is VerdictLabel.INCONCLUSIVE
        assert "NOT CALIBRATED" in bundle.verdict.rationale
        assert "carbon.estimated_tco2e" not in bundle


class TestDirectAgbToCarbonConversion:
    def test_distinct_physical_quantities(self) -> None:
        estimate = convert_agb_to_carbon(
            delta_agb_t_per_ha=20.0,
            area_ha=1_000.0,
            root_to_shoot_ratio=0.25,
            cf=0.50,
            calibration_source="GEDI L4B + Mokany et al. 2006 (TEST-ONLY)",
        )
        assert estimate.delta_agb_t_per_ha == pytest.approx(20.0)
        assert estimate.delta_total_biomass_t_per_ha == pytest.approx(25.0)
        assert estimate.delta_carbon_t_per_ha == pytest.approx(12.5)
        assert estimate.delta_tco2e_per_ha == pytest.approx(12.5 * 44.0 / 12.0)
        assert estimate.cumulative_tco2e == pytest.approx(12.5 * 44.0 / 12.0 * 1_000.0)
        assert estimate.delta_indicator is None

    def test_full_quadrature_error_propagation(self) -> None:
        estimate = convert_agb_to_carbon(
            delta_agb_t_per_ha=20.0,
            area_ha=1_000.0,
            root_to_shoot_ratio=0.25,
            cf=0.50,
            calibration_source="GEDI L4B + Mokany et al. 2006 (TEST-ONLY)",
            agb_std_error_t_per_ha=2.0,  # 10%
            root_to_shoot_se=0.125,  # 0.125 / 1.25 = 10%
            cf_se=0.025,  # 0.025 / 0.50 = 5%
            area_se_ha=50.0,  # 50 / 1000 = 5%
        )
        expected_cv = (0.10**2 + 0.10**2 + 0.05**2 + 0.05**2) ** 0.5
        expected_se = estimate.cumulative_tco2e * expected_cv
        assert estimate.std_error_tco2e == pytest.approx(expected_se)
        assert estimate.uncertainty_lower_tco2e == pytest.approx(
            estimate.cumulative_tco2e - expected_se
        )
        assert estimate.uncertainty_upper_tco2e == pytest.approx(
            estimate.cumulative_tco2e + expected_se
        )

    def test_analytic_95_ci_vs_one_sigma_envelope(self) -> None:
        estimate = convert_agb_to_carbon(
            delta_agb_t_per_ha=20.0,
            area_ha=1_000.0,
            root_to_shoot_ratio=0.25,
            cf=0.50,
            calibration_source="GEDI L4B (TEST-ONLY)",
            agb_std_error_t_per_ha=2.0,
        )
        env = estimate.envelope()
        ci95 = estimate.analytic_95_ci()
        assert env.level == pytest.approx(ONE_SIGMA_LEVEL)
        assert env.kind == ASSUMED_ONE_SIGMA_KIND
        assert ci95.level == pytest.approx(0.95)
        assert ci95.kind == "analytic"
        assert ci95.lower == pytest.approx(
            estimate.cumulative_tco2e - 1.96 * estimate.std_error_tco2e
        )
        assert ci95.upper == pytest.approx(
            estimate.cumulative_tco2e + 1.96 * estimate.std_error_tco2e
        )
        assert (ci95.upper - ci95.lower) > (env.upper - env.lower)

    def test_missing_calibration_source_or_rts_raises(self) -> None:
        with pytest.raises(NotCalibratedError, match="calibration_source"):
            convert_agb_to_carbon(
                delta_agb_t_per_ha=15.0,
                area_ha=500.0,
                root_to_shoot_ratio=0.24,
                calibration_source="   ",
            )
        with pytest.raises(NotCalibratedError, match="root_to_shoot_ratio"):
            convert_agb_to_carbon(
                delta_agb_t_per_ha=15.0,
                area_ha=500.0,
                root_to_shoot_ratio=None,
                calibration_source="TEST-ONLY",
            )

    def test_invalid_inputs_raise_value_error(self) -> None:
        with pytest.raises(ValueError, match="area_ha must be positive"):
            convert_agb_to_carbon(
                10.0, 0.0, root_to_shoot_ratio=0.2, calibration_source="TEST-ONLY"
            )
        with pytest.raises(ValueError, match="root_to_shoot_ratio must be non-negative"):
            convert_agb_to_carbon(
                10.0, 100.0, root_to_shoot_ratio=-0.1, calibration_source="TEST-ONLY"
            )
        with pytest.raises(ValueError, match="cf must be in"):
            convert_agb_to_carbon(
                10.0, 100.0, root_to_shoot_ratio=0.2, cf=1.2, calibration_source="TEST-ONLY"
            )
