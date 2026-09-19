"""End-to-end engine runs, case registry, and observation methodology."""

from __future__ import annotations

import numpy as np
import pytest

from groundtruth.contracts.errors import CaseDefinitionError
from groundtruth.contracts.request import AnalysisWindow
from groundtruth.contracts.result import EngineStatus
from groundtruth.contracts.types import Indicator, VerdictLabel
from groundtruth.engine import run_analysis
from groundtruth.engine.observation.indices import evi, nbr, ndvi
from groundtruth.engine.observation.masking import (
    SCL_INVALID_CLASSES,
    audit_masking,
    composite_median,
    scl_cloud_mask,
)
from groundtruth.engine.observation.zonal import zonal_stats
from groundtruth.platform.cases.registry import get_case, list_cases, load_all_cases
from groundtruth.platform.datasets.access import synthetic_access
from groundtruth.platform.datasets.synthetic import SyntheticObservationProvider, is_synthetic


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
        with pytest.raises(ValueError, match="invalid analysis window"):
            AnalysisWindow(pre_start=2010, pre_end=2005, post_start=2011, post_end=2020)


class TestCaseToRequestTranslation:
    """The platform translates a stored case into the engine input."""

    def test_a_case_converts_to_a_contract_request(self, kariba_case):
        request = kariba_case.to_request()
        assert request.case_id == kariba_case.case_id
        assert request.indicator is kariba_case.indicator
        assert request.window.n_pre_periods == kariba_case.window.n_pre_periods
        assert request.claim.name == kariba_case.claim.name

    def test_the_request_never_carries_the_known_reference(self, kariba_case):
        """Feeding a published third-party figure forward would destroy independence."""
        payload = kariba_case.to_request().model_dump_json()
        assert "known_reference" not in payload
        assert "0.57" not in payload
        assert "Verra investigation" not in payload

    def test_translation_is_stable(self, kariba_case):
        assert kariba_case.to_request().spec_hash == kariba_case.to_request().spec_hash

    def test_every_case_produces_a_valid_request(self):
        for case in load_all_cases().values():
            assert case.to_request().spec_hash


class TestSyntheticProvider:
    def test_provenance_marks_data_as_simulated(self):
        assert is_synthetic(SyntheticObservationProvider().provenance_for(Indicator.NDVI))

    def test_output_is_deterministic_for_a_given_seed(self):
        kwargs = {
            "unit_id": "u",
            "indicator": Indicator.NDVI,
            "start_period": 2001,
            "end_period": 2012,
        }
        a = SyntheticObservationProvider(seed=42).fetch_series(**kwargs)
        b = SyntheticObservationProvider(seed=42).fetch_series(**kwargs)
        assert a.values == b.values

    def test_injected_effect_appears_only_after_the_treatment_period(self):
        kwargs = {
            "unit_id": "treated",
            "indicator": Indicator.NDVI,
            "start_period": 2001,
            "end_period": 2020,
        }
        control = SyntheticObservationProvider(seed=1).fetch_series(**kwargs)
        treated = SyntheticObservationProvider(
            seed=1, treated_unit_id="treated", true_effect=0.1, treatment_period=2011
        ).fetch_series(**kwargs)
        pre = np.array(treated.values[:10]) - np.array(control.values[:10])
        post = np.array(treated.values[10:]) - np.array(control.values[10:])
        assert np.allclose(pre, 0.0, atol=1e-12)
        assert post.mean() > 0.05

    def test_an_inverted_window_is_rejected(self):
        with pytest.raises(ValueError, match="end_period must be after"):
            SyntheticObservationProvider().fetch_series(
                unit_id="u", indicator=Indicator.NDVI, start_period=2012, end_period=2001
            )


class TestObservationMethodology:
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
        assert not scl_cloud_mask(np.array(SCL_INVALID_CLASSES)).any()

    def test_scl_mask_keeps_vegetation_and_bare_soil(self):
        assert scl_cloud_mask(np.array([4, 5, 6])).all()

    def test_median_composite_ignores_nan(self):
        assert composite_median(np.array([[1.0], [np.nan], [3.0]]))[0] == pytest.approx(2.0)

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
    """Run one case through the contract, exactly as the platform does."""
    case = get_case(case_id)
    request = case.to_request(seed=20260101, min_donors=min_donors)
    return run_analysis(request, synthetic_access(request, true_effect=true_effect))


class TestEndToEnd:
    def test_engine_returns_a_completed_result_with_a_verdict(self):
        result = _run("kariba-redd")
        assert result.status is EngineStatus.COMPLETED
        assert result.bundle is not None and result.bundle.verdict is not None
        assert len(result.bundle) > 5

    def test_the_result_carries_reproducibility_identifiers(self):
        result = _run("kariba-redd")
        assert result.run_id.startswith("run_")
        assert result.spec_hash
        assert result.engine.engine_version
        assert result.contract_version

    def test_the_same_request_produces_the_same_estimate(self):
        """Reproducibility is a requirement, not a convenience."""
        first, second = _run("kariba-redd"), _run("kariba-redd")
        assert first.spec_hash == second.spec_hash
        assert first.bundle is not None and second.bundle is not None
        assert first.bundle.numeric_values() == second.bundle.numeric_values()

    def test_simulated_runs_are_flagged_on_the_result(self):
        result = _run("kariba-redd")
        assert result.is_simulated
        assert result.data_mode == "simulated"

    def test_simulated_runs_are_flagged_in_the_warnings(self):
        result = _run("kariba-redd")
        assert result.bundle is not None
        assert any("SIMULATED DATA" in w for w in result.bundle.warnings)

    def test_simulated_runs_are_flagged_in_the_verdict_caveats(self):
        result = _run("kariba-redd")
        assert result.bundle is not None and result.bundle.verdict is not None
        assert any("SIMULATED DATA" in c for c in result.bundle.verdict.caveats)

    def test_no_evidence_item_carries_a_carbon_unit_for_an_index_effect(self):
        """NDVI in, no tCO2e out. The core scientific guard, at the system level."""
        result = _run("kariba-redd")
        assert result.bundle is not None
        effect = result.bundle.require("effect.point_estimate")
        assert effect.unit == "ndvi"
        assert effect.qualifiers["is_carbon_quantity"] is False

    def test_the_verdict_refuses_to_compare_an_index_against_a_tco2e_claim(self):
        result = _run("kariba-redd")
        assert result.bundle is not None and result.bundle.verdict is not None
        assert result.bundle.verdict.label is VerdictLabel.INCONCLUSIVE
        assert "commensurable units" in result.bundle.verdict.rationale

    def test_every_evidence_item_has_complete_provenance(self):
        result = _run("kariba-redd")
        assert result.bundle is not None
        for item in result.bundle.items:
            assert item.provenance.source
            assert item.provenance.method
            assert item.provenance.fingerprint()

    def test_the_report_is_grounded_in_its_own_bundle(self):
        from groundtruth.contracts.grounding import policy_for_bundle, verify_grounding
        from groundtruth.platform.reports.narrative import generate_report

        result = _run("kariba-redd")
        assert result.bundle is not None
        report = generate_report(result.bundle)
        grounding = verify_grounding(
            report.markdown, result.bundle, policy_for_bundle(result.bundle)
        )
        assert grounding.grounded, grounding.summary()

    def test_the_result_round_trips_through_json(self):
        from groundtruth.contracts.result import AnalysisResult

        result = _run("kariba-redd")
        restored = AnalysisResult.model_validate_json(result.model_dump_json())
        assert restored.bundle is not None and result.bundle is not None
        assert restored.bundle.numeric_values() == result.bundle.numeric_values()

    def test_an_underpowered_donor_pool_is_refused_not_raised(self):
        """A domain failure is a typed result the platform can persist and show."""
        result = _run("kariba-redd", min_donors=500)
        assert result.status is EngineStatus.REFUSED
        assert result.error is not None
        assert result.error.code.is_refusal
        assert result.error.remediation

    def test_metrics_are_recorded_for_monitoring(self):
        result = _run("kariba-redd")
        assert result.metrics.duration_ms > 0
        assert result.metrics.n_donors_admitted > 0
        assert result.metrics.stage_durations_ms

    def test_all_three_cases_run_without_raising(self):
        for case_id in ("kariba-redd", "southern-cardamom-redd", "mikoko-pamoja"):
            assert _run(case_id).status is EngineStatus.COMPLETED
