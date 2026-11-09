"""Pre-registered constants and the trend statistics of the assessment engine.

Every threshold below is *provisional*: chosen before looking at any project's result,
covered by tests, and never tuned to reach a conclusion. Changing one is a methodology
change and needs a deliberate review.

The statistics are pure numpy (no new dependency): a Theil-Sen slope with a
distribution-free confidence interval, and a tie-corrected two-sided Mann-Kendall test.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from statistics import NormalDist

import numpy as np

from groundtruth.engine.assessment.types import Limitation

# -- trend gating -----------------------------------------------------------------------

MIN_TREND_PERIODS = 6
"""Annual periods needed before any trend claim. Below it the status is always
``Insufficient evidence``; the observed first-to-last change is still reported."""

TREND_ALPHA = 0.10
"""Two-sided significance level of the Mann-Kendall test, and the (1 - alpha) level of
the Theil-Sen confidence interval (90 %)."""

STABLE_MARGIN_PER_YEAR = 0.005
"""Provisional. Index units per year. A series is ``Stable`` only if the Theil-Sen 90 %
interval lies inside +/- this margin; otherwise, without significance, ``No clear
change``. Roughly 0.015 index units over three years, about the inter-annual noise of a
vegetation index; it is an equivalence margin, not a finding."""

# -- climate ----------------------------------------------------------------------------

CLIMATE_ADJUST_MIN_YEARS = 8
"""Overlapping annual (index, SPI-12) pairs needed to regress the index on climate."""

DROUGHT_SPI = -1.0
WET_SPI = 1.0

# -- coverage ---------------------------------------------------------------------------

COVERAGE_COMPLETE = 95.0
COVERAGE_REVIEW = 50.0

# -- level gating -----------------------------------------------------------------------

MIN_LEVEL_PERIODS = 2
"""Annual periods with a real value needed for Level 1."""

MIN_CLIMATE_OVERLAP_YEARS = 2
"""Observed years that must have real climate values for Level 2 (a series, not a point)."""

MIN_REFERENCE_DONORS = 3
"""Reference areas with an overlapping series for Level 3 and for dimension 6. With fewer,
a rank among donors means little (R5: prefer an honest refusal to a fragile number)."""

MIN_REFERENCE_OVERLAP_PERIODS = 2

LEVEL_NAMES: tuple[str, ...] = (
    "Not assessable",
    "Basic monitoring",
    "Contextual intelligence",
    "Comparative intelligence",
    "Attribution assessment",
    "Verified impact",
)

RISK_SIGNAL_LABEL = "signal — requires field verification"
"""A risk finding is only ever a signal, never a confirmation of damage."""


# -- statistics -------------------------------------------------------------------------


def _as_arrays(years: Sequence[float], values: Sequence[float]) -> tuple[np.ndarray, np.ndarray]:
    x = np.asarray(years, dtype=float)
    y = np.asarray(values, dtype=float)
    if x.shape != y.shape or x.ndim != 1:
        raise ValueError("years and values must be 1-D and the same length")
    if x.size > 1 and not np.all(np.diff(x) > 0):
        raise ValueError("years must be strictly increasing")
    return x, y


def _s_statistic_and_variance(y: np.ndarray) -> tuple[float, float]:
    """Mann-Kendall S and its tie-corrected variance (Kendall 1975)."""
    n = y.size
    i, j = np.triu_indices(n, k=1)
    s = float(np.sum(np.sign(y[j] - y[i])))
    _, counts = np.unique(y, return_counts=True)
    tie_term = float(np.sum(counts * (counts - 1) * (2 * counts + 5)))
    var = (n * (n - 1) * (2 * n + 5) - tie_term) / 18.0
    return s, var


def mann_kendall(values: Sequence[float]) -> float:
    """Two-sided Mann-Kendall p-value (normal approximation, continuity-corrected,
    tie-corrected variance). Returns 1.0 (no evidence of a monotonic trend) when the
    series has fewer than two values or no variance (all tied).

    Caveat: the normal approximation with continuity correction is coarse for n < 10;
    exact tables would be preferable there. The pre-registered rule keeps the normal
    approximation for simplicity and reproducibility."""
    y = np.asarray(values, dtype=float)
    if y.size < 2:
        return 1.0
    s, var = _s_statistic_and_variance(y)
    if var <= 0.0:
        return 1.0
    z = 0.0 if s == 0.0 else (s - math.copysign(1.0, s)) / math.sqrt(var)
    return float(math.erfc(abs(z) / math.sqrt(2.0)))


def theil_sen(
    years: Sequence[float], values: Sequence[float], alpha: float = TREND_ALPHA
) -> tuple[float, float, float]:
    """Theil-Sen slope with a (1 - alpha) distribution-free confidence interval.

    The slope is the median of all pairwise slopes. The interval takes the pairwise
    slopes at the ranks M1 = (N - C)/2 and M2 + 1 = (N + C)/2 + 1, with
    C = z * sqrt(Var(S)) from the tie-corrected Mann-Kendall variance (Sen 1968;
    Gilbert 1987), linearly interpolated between neighbouring ranks and clipped to the
    observed slopes. With fewer than three points the interval is not defined (nan).
    """
    x, y = _as_arrays(years, values)
    n = x.size
    if n < 2:
        raise ValueError("Theil-Sen needs at least two points")
    i, j = np.triu_indices(n, k=1)
    slopes = np.sort((y[j] - y[i]) / (x[j] - x[i]))
    slope = float(np.median(slopes))
    if n < 3:
        return slope, math.nan, math.nan
    _, var = _s_statistic_and_variance(y)
    c = NormalDist().inv_cdf(1.0 - alpha / 2.0) * math.sqrt(max(var, 0.0))
    big_n = slopes.size
    lower_rank = (big_n - c) / 2.0  # 1-based
    upper_rank = (big_n + c) / 2.0 + 1.0
    idx = np.arange(big_n, dtype=float)
    lo = float(np.interp(max(lower_rank - 1.0, 0.0), idx, slopes))
    hi = float(np.interp(min(upper_rank - 1.0, big_n - 1.0), idx, slopes))
    return slope, lo, hi


@dataclass(frozen=True, slots=True)
class TrendResult:
    """Outcome of the pre-registered trend rule for one series."""

    status: str
    limitation: Limitation
    n: int
    first_year: int | None
    last_year: int | None
    first_value: float | None
    last_value: float | None
    change: float | None  # last - first; always reported when n >= 2
    slope: float | None  # per year; only estimated with n >= MIN_TREND_PERIODS
    ci_low: float | None
    ci_high: float | None
    p_value: float | None


def classify_trend(years: Sequence[int], values: Sequence[float]) -> TrendResult:
    """Apply the trend rule. Improving / Deteriorating need n >= MIN_TREND_PERIODS and a
    Mann-Kendall p < TREND_ALPHA; otherwise Stable only if the Theil-Sen interval lies
    inside +/- STABLE_MARGIN_PER_YEAR, else No clear change. Non-finite values are
    dropped; years must be strictly increasing.

    Note: the statistical rule for Improving / Deteriorating is the Mann-Kendall test
    alone (spec 6A). A Mann-Kendall-significant trend can coexist with a Theil-Sen
    interval that includes 0 and is still reported Improving / Deteriorating; the
    interval only governs the Stable decision."""
    pairs = [(int(yr), float(v)) for yr, v in zip(years, values, strict=True) if math.isfinite(v)]
    n = len(pairs)
    if n == 0:
        return TrendResult(
            status="Insufficient evidence",
            limitation="missing_data",
            n=0,
            first_year=None,
            last_year=None,
            first_value=None,
            last_value=None,
            change=None,
            slope=None,
            ci_low=None,
            ci_high=None,
            p_value=None,
        )
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]
    _as_arrays(xs, ys)  # validates ordering

    def result(
        status: str,
        limitation: Limitation,
        slope: float | None = None,
        ci_low: float | None = None,
        ci_high: float | None = None,
        p_value: float | None = None,
    ) -> TrendResult:
        return TrendResult(
            status=status,
            limitation=limitation,
            n=n,
            first_year=xs[0],
            last_year=xs[-1],
            first_value=ys[0],
            last_value=ys[-1],
            change=ys[-1] - ys[0] if n >= 2 else None,
            slope=slope,
            ci_low=ci_low,
            ci_high=ci_high,
            p_value=p_value,
        )

    if n < MIN_TREND_PERIODS:
        return result("Insufficient evidence", "weak_statistical_power")
    slope, lo, hi = theil_sen(xs, ys)
    p = mann_kendall(ys)
    if p < TREND_ALPHA and slope > 0:
        return result("Improving", "none", slope, lo, hi, p)
    if p < TREND_ALPHA and slope < 0:
        return result("Deteriorating", "none", slope, lo, hi, p)
    if lo >= -STABLE_MARGIN_PER_YEAR and hi <= STABLE_MARGIN_PER_YEAR:
        return result("Stable", "none", slope, lo, hi, p)
    return result("No clear change", "weak_statistical_power", slope, lo, hi, p)
