"""Covariate transforms against hand-computed values (issue #18)."""

from __future__ import annotations

import math

import numpy as np
import pytest

from groundtruth.contracts.errors import EstimationError
from groundtruth.engine.features import (
    COVARIATE_TRANSFORMS,
    LOG1P,
    engineer_covariates,
    log1p,
    standardise,
    winsorise,
)
from groundtruth.platform.cases.registry import load_all_cases


class TestLog1p:
    def test_matches_hand_computed_values(self):
        out = log1p([0.0, 1.0, math.e - 1.0, 9.0])
        assert out == pytest.approx([0.0, math.log(2.0), 1.0, math.log(10.0)])

    def test_compresses_large_distances_more_than_small_ones(self):
        near, far = log1p([1.0, 5.0]), log1p([51.0, 55.0])
        assert (near[1] - near[0]) > 5 * (far[1] - far[0])

    def test_refuses_negative_values(self):
        with pytest.raises(EstimationError):
            log1p([1.0, -0.5])

    def test_refuses_non_finite_values(self):
        with pytest.raises(EstimationError):
            log1p([1.0, float("nan")])


class TestWinsorise:
    def test_bounds_come_from_the_reference(self):
        reference = np.arange(0.0, 101.0)  # 0..100: the 10% and 90% quantiles are 10 and 90
        clipped, bounds = winsorise(
            [-5.0, 50.0, 200.0], reference=reference, lower_quantile=0.1, upper_quantile=0.9
        )
        assert bounds == pytest.approx((10.0, 90.0))
        assert clipped == pytest.approx([10.0, 50.0, 90.0])

    def test_without_a_reference_the_values_set_their_own_bounds(self):
        clipped, bounds = winsorise([1.0, 2.0, 3.0], lower_quantile=0.0, upper_quantile=0.5)
        assert bounds == pytest.approx((1.0, 2.0))
        assert clipped == pytest.approx([1.0, 2.0, 2.0])

    @pytest.mark.parametrize(("lower", "upper"), [(0.5, 0.5), (0.9, 0.1), (-0.1, 0.9)])
    def test_invalid_quantiles_are_refused(self, lower, upper):
        with pytest.raises(EstimationError):
            winsorise([1.0, 2.0], lower_quantile=lower, upper_quantile=upper)


class TestStandardise:
    def test_matches_hand_computed_z_scores(self):
        # Reference mean 4, sample SD sqrt(((2-4)^2 + 0 + (6-4)^2) / 2) = 2.
        z, (centre, scale) = standardise([4.0, 8.0], reference=[2.0, 4.0, 6.0])
        assert (centre, scale) == pytest.approx((4.0, 2.0))
        assert z == pytest.approx([0.0, 2.0])

    def test_a_constant_reference_does_not_divide_by_zero(self):
        z, (_, scale) = standardise([3.0, 5.0], reference=[3.0, 3.0, 3.0])
        assert scale == 1.0
        assert z == pytest.approx([0.0, 2.0])


class TestEngineerCovariates:
    def test_applies_the_registered_transform_to_project_and_candidates_alike(self):
        result = engineer_covariates(
            {"road_distance_km": 9.0, "rainfall_mm": 700.0},
            {"a": {"road_distance_km": 0.0, "rainfall_mm": 650.0}, "b": {"rainfall_mm": 720.0}},
            ("road_distance_km", "rainfall_mm"),
        )
        assert result.project == pytest.approx(
            {"road_distance_km": math.log(10.0), "rainfall_mm": 700.0}
        )
        assert result.candidates["a"]["road_distance_km"] == 0.0
        assert "road_distance_km" not in result.candidates["b"]  # missing stays missing
        assert result.candidates["b"]["rainfall_mm"] == 720.0

    def test_records_what_was_done_to_every_covariate(self):
        result = engineer_covariates(
            {"road_distance_km": 1.0, "soil_carbon": 3.0},
            {"a": {"road_distance_km": 2.0, "soil_carbon": 4.0}},
            ("road_distance_km", "soil_carbon"),
        )
        records = {r.covariate: r.as_provenance() for r in result.records}
        assert records["road_distance_km"] == {
            "covariate": "road_distance_km",
            "steps": ["log1p"],
            "registered": True,
        }
        # Unregistered covariates are compared raw, and that is recorded.
        assert records["soil_carbon"]["steps"] == ["identity"]
        assert records["soil_carbon"]["registered"] is False

    def test_inputs_are_not_mutated(self):
        project = {"road_distance_km": 9.0}
        candidates = {"a": {"road_distance_km": 4.0}}
        engineer_covariates(project, candidates, ("road_distance_km",))
        assert project == {"road_distance_km": 9.0}
        assert candidates == {"a": {"road_distance_km": 4.0}}

    def test_every_case_covariate_has_a_registered_transform(self):
        """A case cannot quietly match on a covariate nobody chose a scale for."""
        for case_id, case in load_all_cases().items():
            for key in case.to_request().donors.covariates:
                assert key in COVARIATE_TRANSFORMS, (case_id, key)

    def test_skewed_access_covariates_are_log_scaled(self):
        assert COVARIATE_TRANSFORMS["road_distance_km"] == LOG1P
        assert COVARIATE_TRANSFORMS["population_density"] == LOG1P
