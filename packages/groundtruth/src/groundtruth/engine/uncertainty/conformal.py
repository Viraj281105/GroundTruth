"""Conformal prediction intervals for the post-period gap (numpy only).

Pre-period gaps (treated minus counterfactual) are treated as exchangeable
calibration residuals. This is an approximation for time series: coverage is
only approximate and degrades under trends or autocorrelation.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from groundtruth.contracts.errors import InsufficientDataError


@dataclass(frozen=True)
class ConformalInterval:
    """Interval for the mean post-period gap and per-period bands."""

    lower: float
    upper: float
    point: float
    per_period_lower: np.ndarray
    per_period_upper: np.ndarray
    alpha: float
    method: str
    interpretation: str


def _quantile(scores: np.ndarray, alpha: float) -> float:
    n = scores.size
    k = int(np.ceil((n + 1) * (1 - alpha)))
    if k > n:
        return float("inf")
    return float(np.sort(scores)[k - 1])


def conformal_gap_interval(
    pre_residuals: np.ndarray,
    post_gap: np.ndarray,
    alpha: float = 0.1,
    method: str = "split",
    seed: int = 0,
) -> ConformalInterval:
    """Conformal interval for the post-period gap using pre-period residuals.

    ``method`` is ``"split"`` (random half used for calibration, deterministic in
    ``seed``) or ``"full_sample"`` (all pre residuals as calibration scores; this is NOT jackknife+,
    which needs leave-one-out refits of the counterfactual).
    """
    r = np.asarray(pre_residuals, dtype=float)
    g = np.asarray(post_gap, dtype=float)
    if not 0 < alpha < 1:
        raise ValueError("alpha must be in (0, 1)")
    if r.size < 5 or g.size < 1:
        raise InsufficientDataError("need >=5 pre residuals and >=1 post period")
    if method == "split":
        idx = np.random.default_rng(seed).permutation(r.size)
        cal = np.abs(r[idx[: max(r.size // 2, 2)]])
    elif method == "full_sample":
        cal = np.abs(r)
    else:
        raise ValueError("method must be 'split' or 'full_sample'")
    q = _quantile(cal, alpha)
    if not np.isfinite(q):
        raise InsufficientDataError("too few residuals for the requested alpha")
    # Conservative: the mean keeps the per-period width (errors may be autocorrelated).
    point = float(g.mean())
    text = (
        f"An approximate {round((1 - alpha) * 100)}% interval for the average effect is "
        f"[{point - q:.3g}, {point + q:.3g}]. It assumes pre-period fit errors resemble "
        "post-period errors; it does not prove the effect is causal."
    )
    return ConformalInterval(point - q, point + q, point, g - q, g + q, alpha, method, text)
