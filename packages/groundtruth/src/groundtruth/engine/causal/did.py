"""Difference-in-differences estimation and its identifying assumption.

DiD is used here as a cross-check on synthetic control, not as the primary
estimator. It is cheaper and more transparent, but it rests entirely on the
parallel-trends assumption: absent the intervention, treated and control units
would have moved together.

That assumption is not testable, but its pre-treatment analogue is. This module
always reports a pre-trend divergence diagnostic alongside the estimate, so a
reader can see how much faith the assumption deserves.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from groundtruth.contracts.errors import EstimationError, InsufficientDataError


@dataclass(frozen=True)
class DiDResult:
    """A difference-in-differences estimate with its supporting diagnostics."""

    estimate: float
    treated_pre_mean: float
    treated_post_mean: float
    control_pre_mean: float
    control_post_mean: float
    n_control_units: int
    pre_trend_divergence: float
    """Difference in pre-period slopes (treated minus control), per period.

    Large values invalidate the parallel-trends assumption and therefore the
    estimate; they are reported, never suppressed.
    """
    implied_pre_trend_bias: float = 0.0
    """The level difference the pre-period slope divergence alone would produce.

    The slope is a per-period quantity and the estimate is a level difference,
    so the two cannot be compared directly. Projecting the slope across the gap
    between the pre-period and post-period midpoints puts them in the same
    units, which is what makes the screen below meaningful.
    """
    standard_error: float | None = None

    @property
    def parallel_trends_plausible(self) -> bool:
        """Heuristic screen: could the pre-period drift explain the estimate alone?

        This is a screening aid, not a hypothesis test. It compares the estimate
        against the level bias the observed pre-trend divergence would produce
        on its own if it simply continued.
        """
        if abs(self.estimate) < 1e-12:
            return abs(self.implied_pre_trend_bias) < 1e-12
        return abs(self.implied_pre_trend_bias) < 0.25 * abs(self.estimate)


def _slope(values: np.ndarray) -> float:
    """Least-squares slope of ``values`` against period index."""
    if values.size < 2:
        return 0.0
    x = np.arange(values.size, dtype=float)
    x_centred = x - x.mean()
    denominator = float(np.sum(x_centred**2))
    if denominator < 1e-12:
        return 0.0
    return float(np.sum(x_centred * (values - values.mean())) / denominator)


def estimate_did(
    treated_series: np.ndarray,
    control_matrix: np.ndarray,
    n_pre_periods: int,
    *,
    min_pre_periods: int = 3,
) -> DiDResult:
    """Estimate a two-group, two-period difference-in-differences effect.

    Args:
        treated_series: ``(n_periods,)`` outcomes for the treated unit.
        control_matrix: ``(n_periods, n_controls)`` outcomes for control units.
        n_pre_periods: Number of leading pre-treatment periods.
        min_pre_periods: Minimum pre-periods needed to assess pre-trends.

    Returns:
        A :class:`DiDResult` including the pre-trend divergence diagnostic.
    """
    treated = np.asarray(treated_series, dtype=float)
    controls = np.asarray(control_matrix, dtype=float)

    if controls.ndim != 2:
        raise EstimationError("control_matrix must be two-dimensional (periods x units)")
    if treated.shape[0] != controls.shape[0]:
        raise EstimationError("treated series and control matrix have different period counts")
    if n_pre_periods < min_pre_periods:
        raise InsufficientDataError(
            f"{n_pre_periods} pre-treatment periods is too few to assess parallel trends "
            f"(minimum {min_pre_periods})"
        )
    if n_pre_periods >= treated.shape[0]:
        raise InsufficientDataError("no post-treatment periods available")
    if controls.shape[1] == 0:
        raise EstimationError("at least one control unit is required")

    control_mean = controls.mean(axis=1)

    treated_pre = float(np.mean(treated[:n_pre_periods]))
    treated_post = float(np.mean(treated[n_pre_periods:]))
    control_pre = float(np.mean(control_mean[:n_pre_periods]))
    control_post = float(np.mean(control_mean[n_pre_periods:]))

    estimate = (treated_post - treated_pre) - (control_post - control_pre)
    divergence = _slope(treated[:n_pre_periods]) - _slope(control_mean[:n_pre_periods])

    n_periods = treated.shape[0]
    pre_midpoint = (n_pre_periods - 1) / 2.0
    post_midpoint = (n_pre_periods + n_periods - 1) / 2.0
    implied_bias = divergence * (post_midpoint - pre_midpoint)

    # Standard error across control units, treating each as an independent draw
    # of the control-side change. Cluster-robust inference is a P1 improvement.
    per_unit_change = controls[n_pre_periods:].mean(axis=0) - controls[:n_pre_periods].mean(axis=0)
    standard_error = (
        float(np.std(per_unit_change, ddof=1) / np.sqrt(per_unit_change.size))
        if per_unit_change.size > 1
        else None
    )

    return DiDResult(
        estimate=float(estimate),
        treated_pre_mean=treated_pre,
        treated_post_mean=treated_post,
        control_pre_mean=control_pre,
        control_post_mean=control_post,
        n_control_units=int(controls.shape[1]),
        pre_trend_divergence=float(divergence),
        implied_pre_trend_bias=float(implied_bias),
        standard_error=standard_error,
    )
