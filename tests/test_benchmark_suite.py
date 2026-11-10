"""Validation tests for the independent benchmark suite (non-fabricated, R1/R5/R6/R7/R8)."""

from __future__ import annotations

import json

from groundtruth.engine.benchmark.suite import (
    BenchmarkCaseType,
    BenchmarkVerdict,
    run_independent_benchmark_suite,
)


def test_independent_benchmark_suite_execution() -> None:
    """Synthetic controls run live through the solver; unrun empirical cases fail closed."""
    summary = run_independent_benchmark_suite()
    assert summary.total_cases == 5
    assert summary.passed_cases == 3
    assert summary.failed_cases == 0
    assert summary.unavailable_cases == 2
    assert summary.false_positive_rate == 0.0
    assert summary.false_negative_rate == 0.0
    assert summary.uncertainty_calibration_score == 100.0
    assert summary.reproducibility_confirmed is True


def test_unexecuted_empirical_references_fail_closed_without_carbon_conversion() -> None:
    """Empirical/historical cases without ingested panels report UNAVAILABLE, never fabricated ATT or tC/ha."""
    summary = run_independent_benchmark_suite()
    kasigau = next(r for r in summary.results if r.case_id == "BM-02-POSITIVE-INTERVENTION")
    assert kasigau.case_type == BenchmarkCaseType.POSITIVE_INTERVENTION
    assert kasigau.is_synthetic is False
    assert kasigau.data_origin == "published_literature_benchmark"
    assert (
        kasigau.literature_citation is not None and "Verra VCS 612" in kasigau.literature_citation
    )
    assert kasigau.verdict == BenchmarkVerdict.UNAVAILABLE
    assert kasigau.p_value is None
    assert "UNAVAILABLE" in str(kasigau.estimated_effect)
    assert "tC/ha" not in json.dumps(kasigau.to_dict())

    drought = next(r for r in summary.results if r.case_id == "BM-01-HISTORICAL-DROUGHT")
    assert drought.is_synthetic is False
    assert drought.verdict == BenchmarkVerdict.UNAVAILABLE
    assert drought.p_value is None


def test_negative_control_executes_real_null_panel_flagged_synthetic() -> None:
    """Negative control executes the solver on a null synthetic panel and does not reject."""
    summary = run_independent_benchmark_suite()
    neg = next(r for r in summary.results if r.case_id == "BM-03-NEGATIVE-CONTROL")
    assert neg.case_type == BenchmarkCaseType.NEGATIVE_CONTROL
    assert neg.is_synthetic is True
    assert neg.data_origin == "synthetic_simulated"
    assert neg.p_value is not None and neg.p_value > 0.10
    assert neg.verdict == BenchmarkVerdict.PASSED


def test_synthetic_stress_test_executes_and_recovers_injected_effect() -> None:
    """Synthetic recovery test executes deterministically and is explicitly badged synthetic."""
    summary = run_independent_benchmark_suite()
    stress = next(r for r in summary.results if r.case_id == "BM-05-SYNTHETIC-OVERCREDITING")
    assert stress.is_synthetic is True
    assert stress.data_origin == "synthetic_simulated"
    assert stress.case_type == BenchmarkCaseType.SYNTHETIC_STRESS_TEST
    assert stress.verdict == BenchmarkVerdict.PASSED
    assert stress.p_value is not None and stress.p_value <= 0.15
