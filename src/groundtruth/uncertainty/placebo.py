"""Placebo inference for synthetic control.

With one treated unit there is no sampling distribution to appeal to, so
significance is assessed by permutation: refit the model pretending each donor
in turn was the treated unit, and ask how extreme the real unit's post/pre RMSPE
ratio is within that reference distribution.

Two placebo families are implemented:

- **In-space placebos** reassign treatment to other units. They answer "would a
  gap this large appear for an untreated place?"
- **In-time placebos** move the treatment date earlier within the pre-period.
  They answer "does the model produce a gap even when nothing happened?"
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from groundtruth.causal.synthetic_control import fit_synthetic_control
from groundtruth.core.errors import EstimationError, InsufficientDataError
from groundtruth.logging import get_logger

logger = get_logger("uncertainty.placebo")


@dataclass(frozen=True)
class PlaceboResult:
    """The permutation reference distribution and the resulting p-value."""

    observed_statistic: float
    placebo_statistics: tuple[float, ...]
    p_value: float
    n_placebos: int
    n_failed: int
    statistic_name: str = "post_pre_rmspe_ratio"
    excluded_poor_fit: int = 0

    @property
    def rank(self) -> int:
        """1-based rank of the observed statistic, largest first."""
        return 1 + sum(1 for s in self.placebo_statistics if s > self.observed_statistic)

    @property
    def is_extreme(self) -> bool:
        """True if the observed statistic falls in the top decile of placebos."""
        return self.p_value < 0.10

    def interpretation(self) -> str:
        """A sentence a non-statistician can read without over-claiming."""
        if self.n_placebos == 0:
            return "No placebo distribution could be constructed; significance is unassessed."
        verdict = (
            "larger than most placebo units" if self.is_extreme else "within the placebo range"
        )
        return (
            f"The project's post/pre divergence ratio ranks {self.rank} of "
            f"{self.n_placebos + 1} units and is {verdict} "
            f"(permutation p = {self.p_value:.3f}). This measures how unusual the divergence is "
            "relative to untreated comparison regions; it is not a probability that the project "
            "misreported anything."
        )


def in_space_placebo(
    outcome_matrix: np.ndarray,
    unit_ids: tuple[str, ...],
    treated_index: int,
    n_pre_periods: int,
    *,
    ridge: float = 0.0,
    max_pre_rmspe_multiple: float | None = 5.0,
    min_pre_periods: int = 5,
) -> PlaceboResult:
    """Run in-space placebo inference.

    Args:
        outcome_matrix: ``(n_periods, n_units)`` outcomes for all units.
        unit_ids: Unit identifiers aligned with the matrix columns.
        treated_index: Column index of the genuinely treated unit.
        n_pre_periods: Number of leading pre-treatment periods.
        ridge: L2 penalty passed through to the estimator.
        max_pre_rmspe_multiple: Drop placebo units whose own pre-period fit is
            worse than this multiple of the treated unit's pre-RMSPE. Units the
            model cannot fit before treatment produce meaningless ratios and, if
            retained, inflate the reference distribution's tail.
        min_pre_periods: Minimum pre-periods for each fit.

    Returns:
        A :class:`PlaceboResult` with a one-sided permutation p-value.
    """
    outcomes = np.asarray(outcome_matrix, dtype=float)
    if outcomes.ndim != 2:
        raise EstimationError("outcome_matrix must be two-dimensional (periods x units)")
    if outcomes.shape[1] != len(unit_ids):
        raise EstimationError("unit_ids length does not match outcome_matrix columns")
    n_units = outcomes.shape[1]
    if n_units < 3:
        raise InsufficientDataError(
            "placebo inference needs at least three units (one treated, two donors)"
        )

    def fit_for(index: int) -> tuple[float, float]:
        donor_cols = [j for j in range(n_units) if j != index]
        fit = fit_synthetic_control(
            outcomes[:, index],
            outcomes[:, donor_cols],
            tuple(unit_ids[j] for j in donor_cols),
            n_pre_periods,
            ridge=ridge,
            min_pre_periods=min_pre_periods,
        )
        return fit.rmspe_ratio, fit.pre_rmspe

    observed_ratio, observed_pre_rmspe = fit_for(treated_index)

    statistics: list[float] = []
    failed = 0
    excluded = 0
    for j in range(n_units):
        if j == treated_index:
            continue
        try:
            ratio, pre_rmspe = fit_for(j)
        except (EstimationError, InsufficientDataError) as exc:
            failed += 1
            logger.debug("placebo fit failed for %s: %s", unit_ids[j], exc)
            continue
        if (
            max_pre_rmspe_multiple is not None
            and observed_pre_rmspe > 0
            and pre_rmspe > max_pre_rmspe_multiple * observed_pre_rmspe
        ):
            excluded += 1
            continue
        statistics.append(ratio)

    n_placebos = len(statistics)
    if n_placebos == 0:
        p_value = 1.0
    else:
        # Add-one (Phipson & Smyth) correction: a permutation p-value should
        # never be reported as exactly zero.
        n_at_least = sum(1 for s in statistics if s >= observed_ratio)
        p_value = (n_at_least + 1) / (n_placebos + 1)

    return PlaceboResult(
        observed_statistic=float(observed_ratio),
        placebo_statistics=tuple(float(s) for s in statistics),
        p_value=float(p_value),
        n_placebos=n_placebos,
        n_failed=failed,
        excluded_poor_fit=excluded,
    )


@dataclass(frozen=True)
class InTimePlaceboResult:
    """Result of moving the treatment date back into the pre-period."""

    fake_treatment_index: int
    fake_effect: float
    true_effect: float

    @property
    def passes(self) -> bool:
        """True if the fake effect is small relative to the real one.

        A model that "detects" an effect before anything happened is detecting
        its own misspecification.
        """
        if abs(self.true_effect) < 1e-12:
            return abs(self.fake_effect) < 1e-12
        return abs(self.fake_effect) < 0.5 * abs(self.true_effect)


def in_time_placebo(
    treated_series: np.ndarray,
    donor_matrix: np.ndarray,
    donor_ids: tuple[str, ...],
    n_pre_periods: int,
    fake_treatment_index: int,
    *,
    true_effect: float,
    min_pre_periods: int = 3,
) -> InTimePlaceboResult:
    """Refit with treatment pretended to start at ``fake_treatment_index``.

    Only pre-treatment periods are used, so any effect found is spurious by
    construction.
    """
    if fake_treatment_index >= n_pre_periods:
        raise EstimationError("the fake treatment date must fall inside the pre-treatment period")

    fit = fit_synthetic_control(
        np.asarray(treated_series, dtype=float)[:n_pre_periods],
        np.asarray(donor_matrix, dtype=float)[:n_pre_periods],
        donor_ids,
        fake_treatment_index,
        min_pre_periods=min_pre_periods,
    )
    return InTimePlaceboResult(
        fake_treatment_index=fake_treatment_index,
        fake_effect=fit.average_effect,
        true_effect=float(true_effect),
    )
