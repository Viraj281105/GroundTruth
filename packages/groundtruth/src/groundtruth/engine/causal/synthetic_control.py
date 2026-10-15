"""Synthetic control estimation, in the family of Abadie, Diamond & Hainmueller (2010).

The estimator builds a weighted combination of untreated donor units that tracks
the treated unit through the pre-treatment period, then reads the post-treatment
gap between the treated unit and this synthetic counterfactual as the estimated
effect.

Weights are constrained to the unit simplex (non-negative, summing to one). That
constraint is what makes the method defensible: it forbids extrapolation outside
the convex hull of observed donors, so the counterfactual is always a real,
attainable combination of places that actually exist.

**This is not the full ADH (2010) estimator.** It differs in three ways, each
deliberate and each documented in ``docs/science/causal-inference.md``:

- **No V-matrix.** ADH choose predictor weights ``V`` by a nested optimisation.
  Here the weights are fitted to the pre-treatment outcome path alone, with
  every pre-period weighted equally.
- **No covariate-informed weighting.** Covariates decide *which* donors are
  admitted (``engine.matching``); they do not enter the weight objective.
- **No intercept and no demeaning.** The fit is in levels. If the treated unit
  sits outside the donors' convex hull, the fit carries a constant offset into
  the post-period. ``HullDiagnostic`` detects that condition rather than
  correcting it; Doudchenko-Imbens demeaning would be the correction.

The solver is FISTA (accelerated projected gradient) implemented on numpy alone,
deliberately avoiding a SciPy or CVXPY dependency in the core package.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from groundtruth.contracts.errors import EstimationError, InsufficientDataError

HULL_LEVEL_EXCESS_SD = 0.10
"""Material hull exclusion: the treated pre-period mean lies further than this
many pre-period SDs outside the range of donor pre-period means."""

HULL_ENVELOPE_SHARE = 0.50
"""Material hull exclusion: the treated unit lies outside the per-period donor
envelope in more than this share of pre-treatment periods."""


@dataclass(frozen=True)
class HullDiagnostic:
    """Whether the treated pre-period path can be spanned by the donors.

    Exact containment in the convex hull of the donor paths is equivalent to a
    zero pre-period RMSPE, which noisy data never achieves, so it is not a
    useful test. Two *necessary* conditions are checked instead. When either
    fails, every simplex weighting carries a structural offset:

    - **Level.** Any convex combination's pre-period mean lies within the range
      of donor pre-period means. If the treated mean is outside that range, no
      weighting can match its level, and the post-period gap inherits at least
      ``level_excess`` as a constant bias.
    - **Envelope.** In each period, any convex combination lies between the
      lowest and highest donor. Periods where the treated unit is outside that
      envelope cannot be fitted.

    Attributes:
        level_excess: Distance of the treated pre-period mean outside the range
            of donor pre-period means, in outcome units; ``0.0`` if inside.
        level_excess_sd: ``level_excess`` in units of the treated pre-period SD.
        share_periods_outside_envelope: Share of pre-periods where the treated
            unit lies outside the per-period donor min/max envelope.
        max_envelope_excess: Largest per-period distance outside the envelope,
            in outcome units.
    """

    level_excess: float
    level_excess_sd: float
    share_periods_outside_envelope: float
    max_envelope_excess: float

    @property
    def materially_outside(self) -> bool:
        """True if the hull exclusion is large enough to bias the estimate."""
        return (
            self.level_excess_sd > HULL_LEVEL_EXCESS_SD
            or self.share_periods_outside_envelope > HULL_ENVELOPE_SHARE
        )


def _outcome_sd(values: np.ndarray) -> float:
    return float(np.std(values, ddof=1)) if values.size > 1 else 0.0


def convex_hull_diagnostic(treated_pre: np.ndarray, donors_pre: np.ndarray) -> HullDiagnostic:
    """Check the treated pre-period path against the donors' convex hull.

    Args:
        treated_pre: ``(n_pre,)`` treated outcomes before treatment.
        donors_pre: ``(n_pre, n_donors)`` donor outcomes before treatment.
    """
    treated_mean = float(treated_pre.mean())
    donor_means = donors_pre.mean(axis=0)
    level_excess = max(
        float(donor_means.min()) - treated_mean, treated_mean - float(donor_means.max()), 0.0
    )

    below = donors_pre.min(axis=1) - treated_pre
    above = treated_pre - donors_pre.max(axis=1)
    per_period = np.maximum(np.maximum(below, above), 0.0)

    sd = _outcome_sd(treated_pre)
    if sd > 1e-12:
        level_excess_sd = level_excess / sd
    else:
        level_excess_sd = float("inf") if level_excess > 1e-12 else 0.0

    return HullDiagnostic(
        level_excess=level_excess,
        level_excess_sd=float(level_excess_sd),
        share_periods_outside_envelope=float(np.mean(per_period > 0.0)),
        max_envelope_excess=float(per_period.max()),
    )


@dataclass(frozen=True)
class SyntheticControlFit:
    """Fitted weights and diagnostics for one synthetic control."""

    weights: np.ndarray
    donor_ids: tuple[str, ...]
    pre_rmspe: float
    post_rmspe: float
    treated_pre: np.ndarray
    synthetic_pre: np.ndarray
    treated_post: np.ndarray
    synthetic_post: np.ndarray
    n_iterations: int
    converged: bool
    n_pre_periods: int = 0
    hull: HullDiagnostic | None = None

    @property
    def pre_outcome_sd(self) -> float:
        """Sample SD of the treated unit's pre-treatment outcome."""
        return _outcome_sd(self.treated_pre)

    @property
    def relative_pre_fit(self) -> float:
        """Pre-period RMSPE as a share of the pre-period outcome SD.

        Scaling by the SD rather than the mean is what makes the fit gate bite on
        a spectral index: NDVI around 0.6 with year-to-year variation of 0.03
        would pass a mean-scaled 30% gate with an RMSPE of 0.18, six times the
        variation the fit is supposed to explain. ``1 - relative_pre_fit**2`` is
        roughly the pre-period R-squared of the synthetic path.
        """
        sd = self.pre_outcome_sd
        if sd < 1e-12:
            return float("inf") if self.pre_rmspe > 1e-12 else 0.0
        return float(self.pre_rmspe / sd)

    @property
    def weights_are_identified(self) -> bool:
        """True if the donor weights are uniquely determined by the pre-period fit.

        With more donors than pre-treatment periods the fitting problem is
        rank-deficient: many different weight vectors reproduce the treated
        unit's pre-period path exactly as well. The *counterfactual path* is
        still well determined, and so is the effect estimate, but the
        attribution of weight to individual donors is not. Reports must not
        present an unidentified weight vector as if it named the comparison
        regions definitively.
        """
        return self.n_pre_periods >= len(self.donor_ids)

    @property
    def gap_post(self) -> np.ndarray:
        """Per-period post-treatment gap, treated minus synthetic."""
        return self.treated_post - self.synthetic_post

    @property
    def gap_pre(self) -> np.ndarray:
        """Per-period pre-treatment gap; should be close to zero for a good fit."""
        return self.treated_pre - self.synthetic_pre

    @property
    def average_effect(self) -> float:
        """Mean post-treatment gap: the point estimate of the effect."""
        return float(np.mean(self.gap_post))

    @property
    def cumulative_effect(self) -> float:
        """Summed post-treatment gap across periods."""
        return float(np.sum(self.gap_post))

    @property
    def rmspe_ratio(self) -> float:
        """Post/pre RMSPE ratio, the standard synthetic-control test statistic.

        A large ratio means the post-period divergence is large *relative to how
        well the model fitted before treatment*, which is the property that makes
        the placebo test meaningful.
        """
        if self.pre_rmspe < 1e-12:
            return float("inf") if self.post_rmspe > 1e-12 else 0.0
        return float(self.post_rmspe / self.pre_rmspe)

    def contributing_donors(self, threshold: float = 1e-3) -> dict[str, float]:
        """Donors with non-trivial weight, descending.

        Synthetic control solutions are typically sparse; reporting the handful
        of places that actually constitute the counterfactual is what makes the
        result interpretable to a non-statistician.
        """
        pairs = [
            (uid, float(w))
            for uid, w in zip(self.donor_ids, self.weights, strict=True)
            if w > threshold
        ]
        return dict(sorted(pairs, key=lambda kv: kv[1], reverse=True))


def _project_to_simplex(v: np.ndarray) -> np.ndarray:
    """Euclidean projection of ``v`` onto the probability simplex.

    Implements the sorting algorithm of Duchi et al. (2008).
    """
    n = v.size
    u = np.sort(v)[::-1]
    cumulative = np.cumsum(u)
    rho_candidates = u - (cumulative - 1.0) / np.arange(1, n + 1)
    positive = np.nonzero(rho_candidates > 0)[0]
    if positive.size == 0:
        out = np.zeros(n)
        out[int(np.argmax(v))] = 1.0
        return out
    rho = int(positive[-1])
    theta = (cumulative[rho] - 1.0) / (rho + 1)
    return np.maximum(v - theta, 0.0)


def solve_simplex_least_squares(
    donors: np.ndarray,
    treated: np.ndarray,
    *,
    max_iterations: int = 5000,
    tolerance: float = 1e-9,
    ridge: float = 0.0,
) -> tuple[np.ndarray, int, bool]:
    """Minimise ``||treated - donors @ w||^2`` subject to ``w >= 0, sum(w) == 1``.

    Uses FISTA: projected gradient descent with Nesterov momentum. Plain
    projected gradient converges too slowly here because the donor matrix is
    strongly rank-deficient (far more donors than pre-treatment periods), which
    makes the objective almost flat along many directions. Acceleration turns
    that from thousands of iterations into tens.

    Args:
        donors: ``(n_periods, n_donors)`` pre-treatment donor outcomes.
        treated: ``(n_periods,)`` pre-treatment treated outcomes.
        max_iterations: Iteration cap for the optimisation loop.
        tolerance: Convergence threshold on the weight update norm.
        ridge: Optional L2 penalty that spreads weight across similar donors,
            reducing the variance of a sparse solution.

    Returns:
        ``(weights, n_iterations, converged)``.
    """
    n_periods, n_donors = donors.shape
    if treated.shape[0] != n_periods:
        raise EstimationError("treated and donor matrices disagree on the number of periods")
    if n_donors == 0:
        raise EstimationError("cannot fit a synthetic control with zero donors")

    gram = donors.T @ donors + ridge * np.eye(n_donors)
    cross = donors.T @ treated
    # Lipschitz constant of the quadratic objective gives a safe step size.
    lipschitz = float(np.linalg.eigvalsh(gram).max())
    step = 1.0 / lipschitz if lipschitz > 1e-12 else 1.0

    def objective(w: np.ndarray) -> float:
        return float(0.5 * w @ gram @ w - cross @ w)

    weights = np.full(n_donors, 1.0 / n_donors)
    momentum = weights.copy()
    t_k = 1.0
    previous_objective = objective(weights)
    converged = False
    iteration = 0

    for iteration in range(1, max_iterations + 1):  # noqa: B007 - reported as n_iterations
        gradient = gram @ momentum - cross
        candidate = _project_to_simplex(momentum - step * gradient)

        t_next = 0.5 * (1.0 + np.sqrt(1.0 + 4.0 * t_k * t_k))
        extrapolated = candidate + ((t_k - 1.0) / t_next) * (candidate - weights)
        # The extrapolated point may leave the simplex; project it back so the
        # gradient is always evaluated at a feasible point.
        momentum = _project_to_simplex(extrapolated)
        weights, t_k = candidate, t_next

        # Convergence is assessed on the objective, not on the weights. When
        # there are more donors than pre-treatment periods the objective has a
        # flat valley of exactly-equivalent weight vectors, so the weights can
        # keep drifting after the fit has stopped improving. The fit is what
        # the estimate depends on; see `weights_are_identified`.
        current_objective = objective(weights)
        if abs(previous_objective - current_objective) < tolerance * max(
            abs(previous_objective), 1.0
        ):
            converged = True
            break
        previous_objective = current_objective

    return weights, iteration, converged


def fit_synthetic_control(
    treated_series: np.ndarray,
    donor_matrix: np.ndarray,
    donor_ids: tuple[str, ...],
    n_pre_periods: int,
    *,
    ridge: float = 0.0,
    min_pre_periods: int = 5,
) -> SyntheticControlFit:
    """Fit a synthetic control and return the fit with diagnostics.

    Args:
        treated_series: ``(n_periods,)`` outcomes for the treated unit.
        donor_matrix: ``(n_periods, n_donors)`` outcomes for the donor pool.
        donor_ids: Donor identifiers, aligned with ``donor_matrix`` columns.
        n_pre_periods: Number of leading periods before the intervention.
        ridge: L2 penalty on the weights.
        min_pre_periods: Refuse to fit with fewer pre-periods than this.

    Raises:
        InsufficientDataError: if the pre-period is too short to identify weights,
            or there are no post-treatment periods to evaluate.
        EstimationError: on shape mismatches or non-finite inputs.
    """
    treated = np.asarray(treated_series, dtype=float)
    donors = np.asarray(donor_matrix, dtype=float)

    if donors.ndim != 2:
        raise EstimationError("donor_matrix must be two-dimensional (periods x donors)")
    if donors.shape[1] != len(donor_ids):
        raise EstimationError("donor_ids length does not match donor_matrix columns")
    if treated.shape[0] != donors.shape[0]:
        raise EstimationError("treated series and donor matrix have different period counts")
    if not np.isfinite(treated).all() or not np.isfinite(donors).all():
        raise EstimationError(
            "non-finite values in the outcome matrix; impute or drop cloud-starved periods "
            "explicitly before estimation"
        )
    if n_pre_periods < min_pre_periods:
        raise InsufficientDataError(
            f"{n_pre_periods} pre-treatment periods is below the minimum of {min_pre_periods}; "
            "a short pre-period cannot distinguish a good fit from an overfit one"
        )
    if n_pre_periods >= treated.shape[0]:
        raise InsufficientDataError("no post-treatment periods available to evaluate an effect")

    treated_pre, treated_post = treated[:n_pre_periods], treated[n_pre_periods:]
    donors_pre, donors_post = donors[:n_pre_periods], donors[n_pre_periods:]

    weights, iterations, converged = solve_simplex_least_squares(
        donors_pre, treated_pre, ridge=ridge
    )

    synthetic_pre = donors_pre @ weights
    synthetic_post = donors_post @ weights
    pre_rmspe = float(np.sqrt(np.mean((treated_pre - synthetic_pre) ** 2)))
    post_rmspe = float(np.sqrt(np.mean((treated_post - synthetic_post) ** 2)))

    return SyntheticControlFit(
        weights=weights,
        donor_ids=donor_ids,
        pre_rmspe=pre_rmspe,
        post_rmspe=post_rmspe,
        treated_pre=treated_pre,
        synthetic_pre=synthetic_pre,
        treated_post=treated_post,
        synthetic_post=synthetic_post,
        n_iterations=iterations,
        converged=converged,
        n_pre_periods=n_pre_periods,
        hull=convex_hull_diagnostic(treated_pre, donors_pre),
    )
