"""Statistics and named constants of the assessment engine.

The expected numbers below are worked out by hand in the comments, so the
implementation is checked against arithmetic rather than against itself.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

pytest.importorskip("hypothesis")
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from groundtruth.engine.assessment import rules

Z90 = 1.6448536269514722  # two-sided 90 % normal quantile


def _p_from_z(z: float) -> float:
    return math.erfc(abs(z) / math.sqrt(2.0))


def test_constants_are_the_pre_registered_values():
    assert rules.MIN_TREND_PERIODS == 6
    assert rules.TREND_ALPHA == 0.10
    assert rules.STABLE_MARGIN_PER_YEAR == 0.005
    assert rules.CLIMATE_ADJUST_MIN_YEARS == 8
    assert rules.DROUGHT_SPI == -1.0
    assert rules.WET_SPI == 1.0
    assert rules.COVERAGE_COMPLETE == 95.0
    assert rules.COVERAGE_REVIEW == 50.0
    assert rules.LEVEL_NAMES == (
        "Not assessable",
        "Basic monitoring",
        "Contextual intelligence",
        "Comparative intelligence",
        "Attribution assessment",
        "Verified impact",
    )


def test_theil_sen_and_mann_kendall_against_known_values():
    # No ties: x = 0..4, y = 1..5.  Every pairwise slope is 1, so Sen slope = 1.
    # S = 10, Var(S) = 5*4*15/18 = 50/3, z = (10-1)/sqrt(50/3).
    years = [0, 1, 2, 3, 4]
    y = [1.0, 2.0, 3.0, 4.0, 5.0]
    slope, lo, hi = rules.theil_sen(years, y)
    assert (slope, lo, hi) == (1.0, 1.0, 1.0)
    assert rules.mann_kendall(y) == pytest.approx(_p_from_z(9 / math.sqrt(50 / 3)), rel=1e-12)
    assert rules.mann_kendall(y) == pytest.approx(0.0275, abs=5e-4)

    # With a tie: y = [1, 2, 2, 3, 4].
    # Ten pairwise slopes, sorted: 0, 1/2, 1/2, 2/3, 2/3, 3/4, 1, 1, 1, 1 -> median
    # (2/3 + 3/4) / 2 = 17/24.  S = 9 (the (1,2) pair is a tie and contributes 0).
    # One tie group of size 2: Var(S) = (5*4*15 - 2*1*9)/18 = 282/18.
    # z = (9-1)/sqrt(282/18).  N = 10 slopes, C = z90*sqrt(Var), M1 = (N-C)/2,
    # M2 = (N+C)/2; lower bound at 1-based position M1 (interpolated between the
    # 1st and 2nd sorted slopes, 0 and 1/2), upper at M2+1 (all slopes there are 1).
    y2 = [1.0, 2.0, 2.0, 3.0, 4.0]
    var = 282 / 18
    c = Z90 * math.sqrt(var)
    m1 = (10 - c) / 2
    expected_lo = 0.5 * (m1 - 1)  # between sorted[0]=0 and sorted[1]=0.5
    slope2, lo2, hi2 = rules.theil_sen(years, y2)
    assert slope2 == pytest.approx(17 / 24, rel=1e-12)
    assert lo2 == pytest.approx(expected_lo, rel=1e-9)
    assert hi2 == pytest.approx(1.0)
    assert rules.mann_kendall(y2) == pytest.approx(_p_from_z(8 / math.sqrt(var)), rel=1e-12)
    assert rules.mann_kendall(y2) == pytest.approx(0.0433, abs=5e-4)


def test_mann_kendall_degenerate_inputs_return_no_evidence():
    assert rules.mann_kendall([0.3, 0.3, 0.3, 0.3]) == 1.0  # all tied: variance 0
    assert rules.mann_kendall([0.3]) == 1.0
    assert rules.mann_kendall([]) == 1.0


def test_mann_kendall_is_symmetric_in_direction():
    up = [1.0, 3.0, 2.0, 5.0, 4.0, 7.0]
    down = [-v for v in up]
    assert rules.mann_kendall(up) == pytest.approx(rules.mann_kendall(down))


def test_theil_sen_rejects_non_increasing_years():
    with pytest.raises(ValueError):
        rules.theil_sen([2021, 2021, 2022], [0.1, 0.2, 0.3])


def test_classify_trend_below_min_periods_reports_change_only():
    t = rules.classify_trend([2021, 2022, 2023], [0.30, 0.31, 0.34])
    assert t.status == "Insufficient evidence"
    assert t.limitation == "weak_statistical_power"
    assert t.change == pytest.approx(0.04)
    assert t.n == 3
    assert t.slope is None  # no trend is estimated below the minimum


def test_classify_trend_improving_only_when_significant():
    years = list(range(2016, 2024))
    rising = rules.classify_trend(years, [0.30 + 0.01 * i for i in range(8)])
    assert rising.status == "Improving"
    assert rising.p_value is not None and rising.p_value < rules.TREND_ALPHA

    falling = rules.classify_trend(years, [0.50 - 0.01 * i for i in range(8)])
    assert falling.status == "Deteriorating"

    noisy = rules.classify_trend(years, [0.30, 0.34, 0.28, 0.33, 0.29, 0.35, 0.30, 0.31])
    assert noisy.status in {"Stable", "No clear change"}
    assert noisy.status == "No clear change"  # CI far wider than the stable margin


def test_classify_trend_stable_requires_ci_inside_margin():
    years = list(range(2016, 2024))
    tiny = [0.300 + d for d in (0.001, -0.001, 0.0005, -0.0005, 0.001, -0.001, 0.0005, -0.0005)]
    t = rules.classify_trend(years, tiny)
    assert t.status == "Stable"
    assert t.ci_low is not None and t.ci_high is not None
    assert -rules.STABLE_MARGIN_PER_YEAR <= t.ci_low <= t.ci_high <= rules.STABLE_MARGIN_PER_YEAR


def test_classify_trend_ignores_non_finite_values():
    t = rules.classify_trend([2021, 2022, 2023], [0.3, float("nan"), 0.32])
    assert t.n == 2
    assert t.change == pytest.approx(0.02)


@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    st.lists(
        st.floats(min_value=-1.0, max_value=1.0, allow_nan=False),
        min_size=0,
        max_size=rules.MIN_TREND_PERIODS - 1,
    ),
    st.integers(min_value=1990, max_value=2020),
)
def test_no_improving_status_without_statistical_rule(values, start):
    years = [start + i for i in range(len(values))]
    t = rules.classify_trend(years, values)
    assert t.status not in {"Improving", "Deteriorating"}


def test_theil_sen_matches_brute_force_median_on_random_series():
    rng = np.random.default_rng(7)
    y = rng.normal(size=9)
    x = np.arange(9)
    slopes = sorted((y[j] - y[i]) / (x[j] - x[i]) for i in range(9) for j in range(i + 1, 9))
    slope, lo, hi = rules.theil_sen(list(x), list(y))
    assert slope == pytest.approx(float(np.median(slopes)))
    assert lo <= slope <= hi
