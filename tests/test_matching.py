"""Tests for donor-pool construction."""

from __future__ import annotations

import pytest

from groundtruth.core.errors import DonorPoolError
from groundtruth.matching.donors import MatchingConfig, match_donors

COVARIATES = ("rainfall_mm", "elevation_m", "slope_deg", "road_distance_km", "population_density")
PROJECT = {
    "rainfall_mm": 850.0,
    "elevation_m": 750.0,
    "slope_deg": 8.0,
    "road_distance_km": 20.0,
    "population_density": 30.0,
}


def make_candidates(n: int, rng, *, spread: float = 1.0) -> dict[str, dict[str, float]]:
    scales = {
        "rainfall_mm": 120.0,
        "elevation_m": 180.0,
        "slope_deg": 2.5,
        "road_distance_km": 7.0,
        "population_density": 10.0,
    }
    return {
        f"donor-{i:03d}": {
            k: float(PROJECT[k] + spread * scales[k] * rng.normal()) for k in COVARIATES
        }
        for i in range(n)
    }


class TestMatchDonors:
    def test_admits_a_well_specified_pool(self, rng):
        pool = match_donors("project", PROJECT, make_candidates(40, rng))
        assert len(pool.admitted) >= 10
        assert all(m.exclusion_reason is None for m in pool.admitted)

    def test_admitted_donors_are_sorted_by_distance(self, rng):
        pool = match_donors("project", PROJECT, make_candidates(40, rng))
        distances = [m.distance for m in pool.admitted]
        assert distances == sorted(distances)

    def test_leakage_belt_units_are_excluded_with_a_reason(self, rng):
        candidates = make_candidates(40, rng)
        contaminated = {"donor-000", "donor-001"}
        pool = match_donors(
            "project",
            PROJECT,
            candidates,
            MatchingConfig(excluded_unit_ids=frozenset(contaminated)),
        )
        excluded_ids = {m.unit_id for m in pool.excluded}
        assert contaminated <= excluded_ids
        for m in pool.excluded:
            if m.unit_id in contaminated:
                assert "leakage belt" in (m.exclusion_reason or "")

    def test_common_support_caliper_excludes_outliers(self, rng):
        candidates = make_candidates(40, rng)
        candidates["outlier"] = dict(PROJECT)
        candidates["outlier"]["rainfall_mm"] = 100000.0
        pool = match_donors("project", PROJECT, candidates, MatchingConfig(caliper_sd=2.0))
        outlier = next(m for m in pool.matches if m.unit_id == "outlier")
        assert not outlier.admitted
        assert "common support" in (outlier.exclusion_reason or "")

    def test_sparse_pre_period_coverage_excludes_a_candidate(self, rng):
        candidates = make_candidates(40, rng)
        coverage = dict.fromkeys(candidates, 10)
        coverage["donor-005"] = 1
        pool = match_donors("project", PROJECT, candidates, candidate_pre_observations=coverage)
        starved = next(m for m in pool.matches if m.unit_id == "donor-005")
        assert not starved.admitted
        assert "clear pre-treatment observations" in (starved.exclusion_reason or "")

    def test_max_donors_cap_is_applied_by_distance_rank(self, rng):
        pool = match_donors(
            "project", PROJECT, make_candidates(60, rng), MatchingConfig(max_donors=15)
        )
        assert len(pool.admitted) == 15
        capped = [m for m in pool.excluded if "max_donors" in (m.exclusion_reason or "")]
        assert capped

    def test_refuses_an_underpowered_pool_rather_than_estimating(self, rng):
        """Refusing is the correct behaviour; a 3-donor counterfactual is not defensible."""
        with pytest.raises(DonorPoolError, match="admissible donors"):
            match_donors("project", PROJECT, make_candidates(5, rng), MatchingConfig(min_donors=10))

    def test_rejects_an_empty_candidate_set(self):
        with pytest.raises(DonorPoolError, match="no candidate donors"):
            match_donors("project", PROJECT, {})

    def test_rejects_a_project_missing_covariates(self, rng):
        with pytest.raises(DonorPoolError, match="missing covariates"):
            match_donors("project", {"rainfall_mm": 1.0}, make_candidates(30, rng))

    def test_rejects_candidates_missing_the_covariate_set(self):
        with pytest.raises(DonorPoolError, match="full covariate set"):
            match_donors("project", PROJECT, {"d1": {"rainfall_mm": 800.0}})


class TestBalance:
    def test_a_tight_pool_is_balanced(self, rng):
        pool = match_donors("project", PROJECT, make_candidates(80, rng, spread=0.6))
        assert pool.is_balanced
        assert pool.worst_balance <= 0.25

    def test_balance_is_reported_for_every_covariate(self, rng):
        pool = match_donors("project", PROJECT, make_candidates(40, rng))
        assert set(pool.standardised_mean_differences) == set(COVARIATES)

    def test_a_systematically_shifted_pool_is_unbalanced(self, rng):
        candidates = make_candidates(40, rng)
        for cov in candidates.values():
            cov["rainfall_mm"] += 600.0
        pool = match_donors(
            "project", PROJECT, candidates, MatchingConfig(caliper_sd=None, min_donors=5)
        )
        assert not pool.is_balanced
