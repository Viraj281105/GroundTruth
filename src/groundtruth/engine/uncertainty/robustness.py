"""Robustness checks and interval construction.

A single point estimate from a single specification is not evidence. This module
produces the spread of estimates that a reviewer actually needs: what happens
when the most influential donor is removed, when the estimator changes, and how
wide the permutation-implied interval is.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from groundtruth.contracts.errors import EstimationError, InsufficientDataError
from groundtruth.contracts.types import Confidence
from groundtruth.engine.causal.synthetic_control import fit_synthetic_control
from groundtruth.logging import get_logger

logger = get_logger("uncertainty.robustness")


@dataclass(frozen=True)
class LeaveOneOutResult:
    """Sensitivity of the estimate to removing each contributing donor."""

    baseline_effect: float
    effects: dict[str, float]

    @property
    def min_effect(self) -> float:
        """Smallest effect across the leave-one-out refits."""
        return min(self.effects.values()) if self.effects else self.baseline_effect

    @property
    def max_effect(self) -> float:
        """Largest effect across the leave-one-out refits."""
        return max(self.effects.values()) if self.effects else self.baseline_effect

    @property
    def max_absolute_shift(self) -> float:
        """Largest absolute change in the estimate caused by dropping one donor."""
        if not self.effects:
            return 0.0
        return max(abs(v - self.baseline_effect) for v in self.effects.values())

    @property
    def sign_is_stable(self) -> bool:
        """True if every refit keeps the sign of the baseline effect.

        A sign flip means the finding is driven by a single comparison region
        and should not be reported as a project-level conclusion.
        """
        if not self.effects:
            return True
        baseline_sign = np.sign(self.baseline_effect)
        return all(np.sign(v) == baseline_sign for v in self.effects.values())

    def envelope(self, level: float = 0.95) -> Confidence:
        """The leave-one-out range expressed as a sensitivity envelope.

        This is explicitly *not* a confidence interval; ``kind`` records that.
        """
        return Confidence(
            lower=float(self.min_effect),
            upper=float(self.max_effect),
            level=level,
            kind="sensitivity-envelope",
        )


def leave_one_out(
    treated_series: np.ndarray,
    donor_matrix: np.ndarray,
    donor_ids: tuple[str, ...],
    n_pre_periods: int,
    *,
    baseline_effect: float,
    only_contributing: dict[str, float] | None = None,
    min_donors: int = 2,
    min_pre_periods: int = 5,
) -> LeaveOneOutResult:
    """Refit the synthetic control with each donor removed in turn.

    Args:
        treated_series: Outcomes for the treated unit.
        donor_matrix: ``(n_periods, n_donors)`` donor outcomes.
        donor_ids: Donor identifiers.
        n_pre_periods: Number of pre-treatment periods.
        baseline_effect: Effect from the full-pool fit.
        only_contributing: If given, restrict refits to donors that carried
            weight in the baseline fit. Removing a zero-weight donor cannot move
            the estimate, so refitting for it wastes compute.
        min_donors: Minimum donors that must remain for a refit to be attempted.
        min_pre_periods: Passed through to the estimator.
    """
    donors = np.asarray(donor_matrix, dtype=float)
    targets = list(only_contributing) if only_contributing is not None else list(donor_ids)

    effects: dict[str, float] = {}
    for uid in targets:
        if uid not in donor_ids:
            continue
        keep = [j for j, d in enumerate(donor_ids) if d != uid]
        if len(keep) < min_donors:
            continue
        try:
            fit = fit_synthetic_control(
                treated_series,
                donors[:, keep],
                tuple(donor_ids[j] for j in keep),
                n_pre_periods,
                min_pre_periods=min_pre_periods,
            )
        except (EstimationError, InsufficientDataError) as exc:
            logger.debug("leave-one-out refit failed without %s: %s", uid, exc)
            continue
        effects[uid] = fit.average_effect

    return LeaveOneOutResult(baseline_effect=float(baseline_effect), effects=effects)


def permutation_interval(
    observed_effect: float,
    placebo_effects: tuple[float, ...],
    *,
    level: float = 0.95,
) -> Confidence:
    """Build an interval from the spread of placebo effects.

    The placebo effects describe how large a gap the method produces for units
    where no intervention occurred. Centring that spread on the observed effect
    gives an honest range for the treated unit.

    Raises:
        InsufficientDataError: if there are too few placebos to form a spread.
    """
    if len(placebo_effects) < 5:
        raise InsufficientDataError(
            f"only {len(placebo_effects)} placebo effects; at least 5 are needed to form a "
            "permutation interval"
        )
    tail = (1.0 - level) / 2.0
    placebos = np.asarray(placebo_effects, dtype=float)
    lower_q = float(np.quantile(placebos, tail))
    upper_q = float(np.quantile(placebos, 1.0 - tail))
    return Confidence(
        lower=float(observed_effect + lower_q),
        upper=float(observed_effect + upper_q),
        level=level,
        kind="permutation",
    )


@dataclass(frozen=True)
class SpecificationCurve:
    """Estimates across alternative, equally defensible specifications.

    Reporting the curve rather than the single best-looking specification is
    what prevents the analysis from becoming an exercise in motivated fitting.
    """

    estimates: dict[str, float]

    @property
    def median(self) -> float:
        """Median estimate across specifications."""
        return float(np.median(list(self.estimates.values()))) if self.estimates else float("nan")

    @property
    def sign_agreement(self) -> float:
        """Share of specifications agreeing with the median's sign."""
        if not self.estimates:
            return float("nan")
        values = np.asarray(list(self.estimates.values()), dtype=float)
        target = np.sign(self.median)
        return float(np.mean(np.sign(values) == target))

    def envelope(self, level: float = 0.95) -> Confidence:
        """Range across specifications, labelled as a sensitivity envelope."""
        values = list(self.estimates.values())
        return Confidence(
            lower=float(min(values)),
            upper=float(max(values)),
            level=level,
            kind="sensitivity-envelope",
        )
