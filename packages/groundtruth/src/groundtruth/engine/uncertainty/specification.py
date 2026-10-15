"""In-run specification curve: a one-at-a-time sweep around the request's centre.

A single specification can be chosen, consciously or not, because it gives a
satisfying answer. The curve shows whether a finding belongs to the data or to
one analytic choice. The sweep is one-at-a-time around a centre, not a full
factorial, so each deviation can be attributed to the one choice it changed
(``experiments/specification_curve/PLAN.md``).

The centre is the request's own specification. Only choices the engine can
re-make from the panel it already holds are varied here:

- ``ridge``: 0.0, 0.01 and 0.1, the plan's values, minus the centre's own.
- ``pre_period_length``: 8, 10 and 12 periods, only where shorter than the
  centre's; the earliest periods are dropped.
- ``treatment_date``: one period earlier, testing the no-anticipation
  assumption. The plan's validation date is not known to the engine.
- ``donor_cap``: the 20, 35 and 50 nearest donors, only where below the
  admitted pool and at or above ``min_donors``.

Indicator, caliper and covariate weighting need new observations or a re-run of
matching. They belong to the offline experiment and are listed in
``NOT_VARIED_IN_RUN`` so their absence is recorded, not hidden.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from groundtruth.contracts.errors import EstimationError, InsufficientDataError
from groundtruth.engine.causal.synthetic_control import fit_synthetic_control
from groundtruth.engine.uncertainty.robustness import SpecificationCurve

CENTRE_ID = "centre"

RIDGE_VALUES = (0.0, 0.01, 0.1)
PRE_PERIOD_LENGTHS = (8, 10, 12)
DONOR_CAPS = (20, 35, 50)
TREATMENT_SHIFT = 1

NOT_VARIED_IN_RUN = ("indicator", "caliper", "covariate_weighting")
"""Dimensions of the pre-registered curve that need data or matching the run lacks."""


@dataclass(frozen=True)
class Specification:
    """One point on the curve: the centre with at most one choice changed."""

    spec_id: str
    dimension: str
    ridge: float
    leading_periods_dropped: int = 0
    treatment_shift: int = 0
    donor_cap: int | None = None


def _slug(value: float) -> str:
    return f"{value:g}".replace(".", "-")


def build_specifications(
    *,
    ridge: float,
    n_pre: int,
    n_donors: int,
    min_pre_periods: int,
    min_donors: int,
) -> tuple[Specification, ...]:
    """The centre plus every one-at-a-time deviation this panel can support."""
    specs = [Specification(CENTRE_ID, "centre", ridge)]
    specs += [Specification(f"ridge-{_slug(r)}", "ridge", r) for r in RIDGE_VALUES if r != ridge]
    specs += [
        Specification(f"pre-period-{length}", "pre_period_length", ridge, n_pre - length)
        for length in PRE_PERIOD_LENGTHS
        if min_pre_periods <= length < n_pre
    ]
    if n_pre - TREATMENT_SHIFT >= min_pre_periods:
        specs.append(
            Specification(
                f"treatment-{TREATMENT_SHIFT}-earlier",
                "treatment_date",
                ridge,
                treatment_shift=TREATMENT_SHIFT,
            )
        )
    specs += [
        Specification(f"donor-cap-{cap}", "donor_cap", ridge, donor_cap=cap)
        for cap in DONOR_CAPS
        if max(min_donors, 2) <= cap < n_donors
    ]
    return tuple(specs)


def specification_curve(
    treated: np.ndarray,
    donor_matrix: np.ndarray,
    donor_ids: tuple[str, ...],
    n_pre: int,
    *,
    ridge: float = 0.0,
    min_pre_periods: int = 5,
    min_donors: int = 10,
) -> SpecificationCurve:
    """Fit every specification and return the curve.

    Args:
        treated: ``(n_periods,)`` aligned treated outcomes.
        donor_matrix: ``(n_periods, n_donors)`` aligned donor outcomes, columns
            ordered closest donor first, so a cap keeps the nearest donors.
        donor_ids: Donor ids aligned with the columns.
        n_pre: Row index of the first post-treatment period.
        ridge: The centre's ridge penalty.
        min_pre_periods: Floor on pre-periods for every fit.
        min_donors: Floor on donor caps.

    Returns:
        A :class:`SpecificationCurve`. A specification that cannot be estimated
        is recorded in ``failed``, never silently dropped.
    """
    specs = build_specifications(
        ridge=ridge,
        n_pre=n_pre,
        n_donors=len(donor_ids),
        min_pre_periods=min_pre_periods,
        min_donors=min_donors,
    )
    estimates: dict[str, float] = {}
    failed: dict[str, str] = {}
    for spec in specs:
        drop = spec.leading_periods_dropped
        cols = slice(None) if spec.donor_cap is None else slice(0, spec.donor_cap)
        try:
            fit = fit_synthetic_control(
                treated[drop:],
                donor_matrix[drop:, cols],
                donor_ids[cols],
                n_pre - drop - spec.treatment_shift,
                ridge=spec.ridge,
                min_pre_periods=min_pre_periods,
            )
        except (EstimationError, InsufficientDataError) as exc:
            failed[spec.spec_id] = str(exc)
            continue
        estimates[spec.spec_id] = fit.average_effect

    return SpecificationCurve(
        estimates=estimates,
        centre_id=CENTRE_ID,
        dimensions={s.spec_id: s.dimension for s in specs},
        failed=failed,
    )


__all__ = [
    "CENTRE_ID",
    "NOT_VARIED_IN_RUN",
    "Specification",
    "build_specifications",
    "specification_curve",
]
