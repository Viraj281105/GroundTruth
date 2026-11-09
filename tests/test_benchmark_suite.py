"""Tests for GroundTruth 2.0 Scientific Benchmark Suite."""

from __future__ import annotations

from groundtruth.engine.benchmark.suite import (
    BenchmarkCaseType,
    BenchmarkVerdict,
    run_independent_benchmark_suite,
)


def test_independent_benchmark_suite_execution():
    """Verify benchmark suite executes deterministically with all 5 certified cases."""
    summary = run_independent_benchmark_suite()

    assert summary.total_cases == 5
    assert summary.passed_cases == 5
    assert summary.failed_cases == 0
    assert summary.false_positive_rate == 0.0
    assert summary.false_negative_rate == 0.0
    assert summary.uncertainty_calibration_score >= 95.0
    assert summary.reproducibility_confirmed is True


def test_kasigau_reconciliation_provenance():
    """Verify BM-02 Kasigau Corridor benchmark carries explicit literature provenance and reconciled figures."""
    summary = run_independent_benchmark_suite()
    kasigau_case = next(r for r in summary.results if r.case_id == "BM-02-POSITIVE-INTERVENTION")

    assert kasigau_case.case_type == BenchmarkCaseType.POSITIVE_INTERVENTION
    assert kasigau_case.is_synthetic is False
    assert kasigau_case.data_origin == "published_literature_benchmark"
    assert "Verra VCS 612" in kasigau_case.literature_citation
    assert kasigau_case.verdict == BenchmarkVerdict.PASSED

    # Establish authentic figures
    assert kasigau_case.estimated_effect == "ATT = +0.038 NDVI (+1.8 tC/ha)"
    assert kasigau_case.p_value == 0.0020

    # Verify pre-trends parallelism metric confirms 0.082 was the pre-trends p-value
    pre_trend_metric = next(m for m in kasigau_case.metrics if "Pre-Trends" in m.metric_name)
    assert pre_trend_metric.observed_value == 0.082
    assert pre_trend_metric.passed is True


def test_negative_control_zero_false_positive():
    """Verify BM-03 Untreated Savanna produces zero false positive additionality."""
    summary = run_independent_benchmark_suite()
    neg_control = next(r for r in summary.results if r.case_id == "BM-03-NEGATIVE-CONTROL")

    assert neg_control.case_type == BenchmarkCaseType.NEGATIVE_CONTROL
    assert neg_control.p_value == 0.74  # Null effect cannot be rejected
    assert neg_control.verdict == BenchmarkVerdict.PASSED


def test_synthetic_stress_test_flagged():
    """Verify BM-05 is explicitly tagged as synthetic."""
    summary = run_independent_benchmark_suite()
    stress_case = next(r for r in summary.results if r.case_id == "BM-05-SYNTHETIC-OVERCREDITING")

    assert stress_case.is_synthetic is True
    assert stress_case.case_type == BenchmarkCaseType.SYNTHETIC_STRESS_TEST
    assert stress_case.verdict == BenchmarkVerdict.PASSED
