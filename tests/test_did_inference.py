"""Cluster-robust inference for the DiD cross-check (issue #12)."""

from __future__ import annotations

import numpy as np
import pytest

from groundtruth.contracts.errors import EstimationError
from groundtruth.engine import run_analysis
from groundtruth.engine.causal.did import clustered_inference, estimate_did
from groundtruth.platform.cases.registry import get_case
from groundtruth.platform.datasets.access import synthetic_access


def _clustered_panel(rng: np.random.Generator, n_clusters: int, per_cluster: int):
    """Controls whose post-period shift is shared within each cluster."""
    n_periods, n_pre = 16, 8
    n_controls = n_clusters * per_cluster
    labels = [f"c{g}" for g in range(n_clusters) for _ in range(per_cluster)]
    controls = 0.6 + rng.normal(0.0, 0.002, size=(n_periods, n_controls))
    cluster_shock = rng.normal(0.0, 0.03, size=n_clusters)
    controls[n_pre:] += np.repeat(cluster_shock, per_cluster)
    treated = 0.6 + rng.normal(0.0, 0.002, size=n_periods)
    return treated, controls, n_pre, labels


class TestCR1:
    def test_one_unit_per_cluster_reduces_to_the_unclustered_error(self, rng):
        changes = rng.normal(0.0, 0.01, size=20)
        inference = clustered_inference(0.05, changes, None, cluster_level="unit", seed=1)
        classical = float(np.std(changes, ddof=1) / np.sqrt(changes.size))
        assert inference.cr1_standard_error == pytest.approx(classical, rel=1e-12)
        assert inference.n_clusters == 20

    def test_shared_shocks_widen_the_error_once_clusters_are_declared(self, rng):
        treated, controls, n_pre, labels = _clustered_panel(rng, n_clusters=6, per_cluster=5)
        naive = estimate_did(treated, controls, n_pre, seed=7)
        clustered = estimate_did(
            treated, controls, n_pre, clusters=labels, cluster_level="district", seed=7
        )
        assert naive.estimate == clustered.estimate
        assert naive.standard_error is not None and clustered.standard_error is not None
        assert clustered.standard_error > 1.5 * naive.standard_error
        assert clustered.inference is not None
        assert clustered.inference.cluster_level == "district"
        assert clustered.inference.n_clusters == 6

    def test_a_label_per_control_is_required(self, rng):
        with pytest.raises(EstimationError):
            clustered_inference(0.0, rng.normal(size=5), ["a", "b"], cluster_level="x", seed=0)

    def test_a_single_cluster_gives_no_error_rather_than_a_fake_one(self):
        inference = clustered_inference(
            0.0, np.array([0.1, 0.2, 0.3]), ["a", "a", "a"], cluster_level="country", seed=0
        )
        assert inference.cr1_standard_error is None
        assert inference.bootstrap_interval is None


class TestWildClusterBootstrap:
    def test_few_clusters_use_webb_weights_and_many_use_rademacher(self, rng):
        few = clustered_inference(
            0.0, rng.normal(size=8), [str(i // 2) for i in range(8)], cluster_level="x", seed=0
        )
        many = clustered_inference(0.0, rng.normal(size=12), None, cluster_level="unit", seed=0)
        assert few.n_clusters == 4 and few.bootstrap_weights == "webb-6"
        assert many.n_clusters == 12 and many.bootstrap_weights == "rademacher"

    def test_the_interval_is_a_labelled_bootstrap_interval_around_the_estimate(self, rng):
        treated, controls, n_pre, labels = _clustered_panel(rng, n_clusters=8, per_cluster=4)
        result = estimate_did(treated, controls, n_pre, clusters=labels, seed=3)
        assert result.inference is not None
        interval = result.inference.bootstrap_interval
        assert interval is not None
        assert interval.kind == "bootstrap"
        assert interval.lower < result.estimate < interval.upper

    def test_the_same_seed_reproduces_the_interval(self, rng):
        treated, controls, n_pre, labels = _clustered_panel(rng, n_clusters=5, per_cluster=4)
        first = estimate_did(treated, controls, n_pre, clusters=labels, seed=11)
        second = estimate_did(treated, controls, n_pre, clusters=labels, seed=11)
        other = estimate_did(treated, controls, n_pre, clusters=labels, seed=12)
        assert first.inference == second.inference
        assert first.inference is not None and other.inference is not None
        assert first.inference.bootstrap_interval != other.inference.bootstrap_interval

    def test_the_bootstrap_agrees_with_cr1_when_clusters_are_plentiful(self, rng):
        changes = rng.normal(0.0, 0.01, size=60)
        inference = clustered_inference(
            0.0, changes, None, cluster_level="unit", seed=5, n_bootstrap=4999
        )
        assert inference.bootstrap_standard_error is not None
        assert inference.cr1_standard_error is not None
        assert inference.bootstrap_standard_error == pytest.approx(
            inference.cr1_standard_error, rel=0.1
        )


def test_a_run_records_the_clustering_level_it_used():
    request = get_case("kariba-redd").to_request(seed=20260101)
    result = run_analysis(request, synthetic_access(request, true_effect=0.06))
    assert result.bundle is not None
    item = result.bundle.require("crosscheck.did_standard_error")
    assert item.unit == "ndvi"
    assert item.confidence is not None and item.confidence.kind == "bootstrap"
    assert item.qualifiers["cluster_level"] == "unit"
    assert item.qualifiers["independent_units_assumed"] is True
    assert item.qualifiers["control_side_only"] is True
    assert item.provenance.parameters["seed"] == request.seed
    assert "independent draw" in (item.provenance.notes or "")
