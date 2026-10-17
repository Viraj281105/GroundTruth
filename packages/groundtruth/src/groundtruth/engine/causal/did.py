"""Difference-in-differences estimation and its identifying assumption.

DiD is used here as a cross-check on synthetic control, not as the primary
estimator. It is cheaper and more transparent, but it rests entirely on the
parallel-trends assumption: absent the intervention, treated and control units
would have moved together.

That assumption is not testable, but its pre-treatment analogue is. This module
always reports a pre-trend divergence diagnostic alongside the estimate, so a
reader can see how much faith the assumption deserves.

**Inference.** Neighbouring control regions share weather, markets and policy,
so treating each as an independent draw makes the standard error too small.
The standard error is clustered (CR1) on the cluster labels supplied, and a
wild cluster bootstrap gives a second standard error and an interval, because
the few-cluster case, the usual one here, is where CR1 is least reliable.
Webb six-point weights are used below 12 clusters and Rademacher weights at 12
or more.

Both describe **control-side uncertainty only**. With a single treated unit
the treated unit's own idiosyncratic noise cannot be estimated (Conley &
Taber, 2011), so the interval is a lower bound on the true uncertainty. It
supports a cross-check and must not be read as the estimate's full uncertainty.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from groundtruth.contracts.errors import EstimationError, InsufficientDataError
from groundtruth.contracts.types import Confidence

UNIT_CLUSTERS = "unit"
"""Cluster level used when no labels are supplied: each control is its own cluster."""

WEBB_BELOW_CLUSTERS = 12
"""Use Webb six-point weights below this many clusters, Rademacher at or above it."""

_WEBB_WEIGHTS = np.array(
    [-np.sqrt(1.5), -1.0, -np.sqrt(0.5), np.sqrt(0.5), 1.0, np.sqrt(1.5)], dtype=float
)


@dataclass(frozen=True)
class ClusteredInference:
    """Control-side inference on the DiD estimate, at one clustering level."""

    cluster_level: str
    n_clusters: int
    cr1_standard_error: float | None
    bootstrap_standard_error: float | None
    bootstrap_interval: Confidence | None
    bootstrap_weights: str
    n_bootstrap: int


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
    """CR1 standard error at ``inference.cluster_level``. Control-side only."""
    inference: ClusteredInference | None = None

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


def clustered_inference(
    estimate: float,
    per_unit_change: np.ndarray,
    clusters: Sequence[str] | None,
    *,
    cluster_level: str,
    seed: int,
    n_bootstrap: int = 999,
    level: float = 0.95,
) -> ClusteredInference:
    """Cluster-robust inference on the control-side mean change.

    The DiD estimate is the treated change minus the mean control change
    ``d_bar``, so its control-side variance is the variance of ``d_bar``.

    - **CR1:** ``G / (G - 1) * sum_g (sum_{i in g} e_i)^2 / N^2`` with
      ``e_i = d_i - d_bar``. With one unit per cluster this reduces to the
      unclustered ``s^2 / N``.
    - **Wild cluster bootstrap:** each draw multiplies every residual in cluster
      ``g`` by one weight ``w_g``, so within-cluster dependence is preserved.
      The interval is the estimate minus the percentiles of ``d_bar* - d_bar``.

    Args:
        estimate: The DiD point estimate.
        per_unit_change: Post-minus-pre mean change for each control unit.
        clusters: One label per control unit, or ``None`` for one cluster each.
        cluster_level: Name of the clustering level, for provenance.
        seed: Seed for the bootstrap draws, from the request. Required so the
            same request reproduces the same interval.
        n_bootstrap: Number of bootstrap draws.
        level: Interval coverage.
    """
    d = np.asarray(per_unit_change, dtype=float)
    labels = [str(i) for i in range(d.size)] if clusters is None else [str(c) for c in clusters]
    if len(labels) != d.size:
        raise EstimationError("one cluster label is needed per control unit")

    groups = sorted(set(labels))
    index = np.array([groups.index(label) for label in labels])
    n_clusters = len(groups)
    weights_name = "webb-6" if n_clusters < WEBB_BELOW_CLUSTERS else "rademacher"

    if n_clusters < 2:
        return ClusteredInference(cluster_level, n_clusters, None, None, None, weights_name, 0)

    d_bar = float(d.mean())
    residuals = d - d_bar
    cluster_sums = np.bincount(index, weights=residuals, minlength=n_clusters)
    cr1_var = n_clusters / (n_clusters - 1) * float(np.sum(cluster_sums**2)) / d.size**2
    cr1 = float(np.sqrt(cr1_var))

    rng = np.random.default_rng(seed)
    if weights_name == "webb-6":
        draws = rng.choice(_WEBB_WEIGHTS, size=(n_bootstrap, n_clusters))
    else:
        draws = rng.choice(np.array([-1.0, 1.0]), size=(n_bootstrap, n_clusters))
    # Mean of the perturbed residuals: (1/N) * sum_g w_g * S_g.
    shifts = draws @ cluster_sums / d.size
    tail = (1.0 - level) / 2.0
    lower_q, upper_q = (float(q) for q in np.quantile(shifts, [tail, 1.0 - tail]))
    # The estimate subtracts d_bar, so a high d_bar* gives a low estimate.
    interval = Confidence(
        lower=float(estimate - upper_q),
        upper=float(estimate - lower_q),
        level=level,
        kind="bootstrap",
    )
    return ClusteredInference(
        cluster_level=cluster_level,
        n_clusters=n_clusters,
        cr1_standard_error=cr1,
        bootstrap_standard_error=float(np.std(shifts, ddof=1)),
        bootstrap_interval=interval,
        bootstrap_weights=weights_name,
        n_bootstrap=n_bootstrap,
    )


def estimate_did(
    treated_series: np.ndarray,
    control_matrix: np.ndarray,
    n_pre_periods: int,
    *,
    min_pre_periods: int = 3,
    clusters: Sequence[str] | None = None,
    cluster_level: str = UNIT_CLUSTERS,
    seed: int = 0,
    n_bootstrap: int = 999,
) -> DiDResult:
    """Estimate a two-group, two-period difference-in-differences effect.

    Args:
        treated_series: ``(n_periods,)`` outcomes for the treated unit.
        control_matrix: ``(n_periods, n_controls)`` outcomes for control units.
        n_pre_periods: Number of leading pre-treatment periods.
        min_pre_periods: Minimum pre-periods needed to assess pre-trends.
        clusters: One cluster label per control column (district, ecoregion or
            country). ``None`` treats each control as its own cluster, which is
            the independent-draws assumption and understates the error.
        cluster_level: Name of the level the labels describe, for provenance.
        seed: Seed for the wild cluster bootstrap.
        n_bootstrap: Number of bootstrap draws.

    Returns:
        A :class:`DiDResult` including the pre-trend divergence diagnostic and
        clustered inference.
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

    per_unit_change = controls[n_pre_periods:].mean(axis=0) - controls[:n_pre_periods].mean(axis=0)
    inference = clustered_inference(
        float(estimate),
        per_unit_change,
        clusters,
        cluster_level=cluster_level,
        seed=seed,
        n_bootstrap=n_bootstrap,
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
        standard_error=inference.cr1_standard_error,
        inference=inference,
    )
