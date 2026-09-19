"""End-to-end pipeline, case registry, evidence assembly and geospatial tests."""

from __future__ import annotations

import numpy as np
import pytest

from groundtruth.cases.registry import AnalysisWindow, get_case, list_cases, load_all_cases
from groundtruth.core.errors import CaseDefinitionError
from groundtruth.core.types import VerdictLabel
from groundtruth.geospatial.indices import evi, nbr, ndvi
from groundtruth.geospatial.masking import (
    SCL_INVALID_CLASSES,
    audit_masking,
    composite_median,
    scl_cloud_mask,
)
from groundtruth.geospatial.zonal import zonal_stats
from groundtruth.ingestion.base import AreaOfInterest, ObservationRequest
from groundtruth.ingestion.synthetic import (
    SyntheticCovariateProvider,
    SyntheticDonorPoolProvider,
    SyntheticObservationProvider,
    is_synthetic,
)
from groundtruth.pipeline import PipelineConfig, run_verification


class TestCaseRegistry:
    def test_the_three_competition_cases_exist(self):
        assert set(list_cases()) >= {
            "kariba-redd",
            "southern-cardamom-redd",
            "mikoko-pamoja",
        }

    def test_every_case_definition_loads_and_validates(self):
        assert len(load_all_cases()) == len(list_cases())

    def test_no_case_claims_to_be_analysed(self):
        """Guards against a status being promoted without a reviewed run."""
        for case in load_all_cases().values():
            assert not case.is_analysed, f"{case.case_id} claims analysed status"

    def test_unknown_case_raises_with_the_available_list(self):
        with pytest.raises(CaseDefinitionError, match="Available cases"):
            get_case("not-a-case")

    def test_kariba_window_is_ordered_and_long_enough(self, kariba_case):
        assert kariba_case.window.n_pre_periods >= 5
        assert kariba_case.window.n_post_periods >= 1
        assert kariba_case.window.pre_end < kariba_case.window.post_start

    def test_kariba_known_reference_is_marked_third_party(self, kariba_case):
        reference = kariba_case.known_reference
        assert reference
        assert "caveat" in reference
        assert "GroundTruth" in reference["caveat"]

    def test_invalid_window_is_rejected(self):
        with pytest.raises(CaseDefinitionError):
            AnalysisWindow(pre_start=2010, pre_end=2005, post_start=2011, post_end=2020)


class TestSyntheticProvider:
    def test_provenance_marks_data_as_simulated(self):
        provider = SyntheticObservationProvider()
        request = ObservationRequest(
            area=AreaOfInterest(unit_id="u"),
            indicator=get_case("kariba-redd").indicator,
            start_period=2001,
            end_period=2010,
        )
        assert is_synthetic(provider.provenance(request))

    def test_output_is_deterministic_for_a_given_seed(self):
        request = ObservationRequest(
            area=AreaOfInterest(unit_id="u"),
            indicator=get_case("kariba-redd").indicator,
            start_period=2001,
            end_period=2012,
        )
        a = SyntheticObservationProvider(seed=42).fetch(request)
        b = SyntheticObservationProvider(seed=42).fetch(request)
        assert a.values == b.values

    def test_injected_effect_appears_only_after_the_treatment_period(self):
        indicator = get_case("kariba-redd").indicator
        area = AreaOfInterest(unit_id="treated")
        request = ObservationRequest(
            area=area, indicator=indicator, start_period=2001, end_period=2020
        )
        control = SyntheticObservationProvider(seed=1).fetch(request)
        treated = SyntheticObservationProvider(
            seed=1, treated_unit_id="treated", true_effect=0.1, treatment_period=2011
        ).fetch(request)
        pre = np.array(treated.values[:10]) - np.array(control.values[:10])
        post = np.array(treated.values[10:]) - np.array(control.values[10:])
        assert np.allclose(pre, 0.0, atol=1e-12)
        assert post.mean() > 0.05

    def test_observation_request_rejects_an_inverted_window(self):
        with pytest.raises(ValueError, match="end_period must be after"):
            ObservationRequest(
                area=AreaOfInterest(unit_id="u"),
                indicator=get_case("kariba-redd").indicator,
                start_period=2012,
                end_period=2001,
            )


class TestGeospatial:
    def test_ndvi_matches_the_published_formula(self):
        assert ndvi(np.array([0.4]), np.array([0.1]))[0] == pytest.approx(0.6)

    def test_ndvi_is_bounded(self, rng):
        values = ndvi(rng.random(500), rng.random(500))
        assert np.nanmin(values) >= -1.0
        assert np.nanmax(values) <= 1.0

    def test_zero_denominator_yields_nan_rather_than_raising(self):
        assert np.isnan(ndvi(np.array([0.0]), np.array([0.0]))[0])

    def test_evi_and_nbr_are_finite_on_realistic_reflectance(self, rng):
        red, nir, blue, swir = (rng.random(100) * 0.3 for _ in range(4))
        assert np.isfinite(evi(nir, red, blue)).all()
        assert np.isfinite(nbr(nir, swir)).all()

    def test_scl_mask_rejects_every_invalid_class(self):
        scl = np.array(SCL_INVALID_CLASSES)
        assert not scl_cloud_mask(scl).any()

    def test_scl_mask_keeps_vegetation_and_bare_soil(self):
        assert scl_cloud_mask(np.array([4, 5, 6])).all()

    def test_median_composite_ignores_nan(self):
        stack = np.array([[1.0], [np.nan], [3.0]])
        assert composite_median(stack)[0] == pytest.approx(2.0)

    def test_masking_audit_flags_sparse_periods(self):
        report = audit_masking((2001, 2002, 2003), (10, 2, 8), min_observations=4)
        assert report.has_sparse_periods
        assert report.periods_below_threshold == (2002,)

    def test_zonal_stats_report_valid_fraction(self):
        stats = zonal_stats(np.array([1.0, 2.0, np.nan, 4.0]))
        assert stats.n_valid == 3
        assert stats.valid_fraction == pytest.approx(0.75)

    def test_zonal_stats_on_an_empty_zone_do_not_raise(self):
        stats = zonal_stats(np.array([np.nan, np.nan]))
        assert stats.n_valid == 0
        assert np.isnan(stats.mean)


def _run(case_id: str, *, true_effect: float = 0.06, min_donors: int = 10):
    case = get_case(case_id)
    observation = SyntheticObservationProvider(
        seed=20260101,
        treated_unit_id=case.case_id,
        true_effect=true_effect,
        treatment_period=case.window.post_start,
    )
    return run_verification(
        case,
        observation,
        SyntheticCovariateProvider(seed=20260101, project_unit_id=case.case_id),
        SyntheticDonorPoolProvider(),
        config=PipelineConfig(min_donors=min_donors),
    )


class TestEndToEnd:
    def test_pipeline_runs_and_produces_a_verdict(self):
        result = _run("kariba-redd")
        assert result.bundle.verdict is not None
        assert len(result.bundle) > 5

    def test_simulated_runs_are_flagged_in_the_warnings(self):
        result = _run("kariba-redd")
        assert any("SIMULATED DATA" in w for w in result.bundle.warnings)

    def test_simulated_runs_are_flagged_in_the_verdict_caveats(self):
        result = _run("kariba-redd")
        assert result.bundle.verdict is not None
        assert any("SIMULATED DATA" in c for c in result.bundle.verdict.caveats)

    def test_no_evidence_item_carries_a_carbon_unit_for_an_index_effect(self):
        """NDVI in, no tCO2e out. The core scientific guard, at the system level."""
        result = _run("kariba-redd")
        effect = result.bundle.require("effect.point_estimate")
        assert effect.unit == "ndvi"
        assert effect.qualifiers["is_carbon_quantity"] is False

    def test_the_verdict_refuses_to_compare_an_index_against_a_tco2e_claim(self):
        result = _run("kariba-redd")
        assert result.bundle.verdict is not None
        assert result.bundle.verdict.label is VerdictLabel.INCONCLUSIVE
        assert "commensurable units" in result.bundle.verdict.rationale

    def test_every_evidence_item_has_complete_provenance(self):
        result = _run("kariba-redd")
        for item in result.bundle.items:
            assert item.provenance.source
            assert item.provenance.method
            assert item.provenance.fingerprint()

    def test_the_report_is_grounded_in_its_own_bundle(self):
        from groundtruth.reporting.grounding import policy_for_bundle, verify_grounding

        result = _run("kariba-redd")
        report = verify_grounding(
            result.report.markdown, result.bundle, policy_for_bundle(result.bundle)
        )
        assert report.grounded, report.summary()

    def test_the_bundle_round_trips_through_json(self):
        from groundtruth.core.evidence import EvidenceBundle

        result = _run("kariba-redd")
        restored = EvidenceBundle.from_json(result.bundle.to_json())
        assert restored.numeric_values() == result.bundle.numeric_values()

    def test_an_underpowered_donor_pool_is_refused(self):
        from groundtruth.core.errors import DonorPoolError

        with pytest.raises(DonorPoolError):
            _run("kariba-redd", min_donors=500)

    def test_all_three_cases_run_without_error(self):
        for case_id in ("kariba-redd", "southern-cardamom-redd", "mikoko-pamoja"):
            assert _run(case_id).bundle.verdict is not None
