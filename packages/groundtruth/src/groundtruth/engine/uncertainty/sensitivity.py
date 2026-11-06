"""Sensitivity to unmeasured confounding: E-value and a simple bound."""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt


@dataclass(frozen=True)
class EValue:
    """E-value (VanderWeele & Ding 2017) for a risk/effect ratio."""

    ratio: float
    e_value_point: float
    e_value_ci: float | None
    interpretation: str


@dataclass(frozen=True)
class ConfounderBound:
    """Effect remaining after removing a hypothetical confounder's contribution."""

    observed_effect: float
    confounder_bias: float
    adjusted_effect: float
    breaks_sign: bool
    interpretation: str


def _ev(rr: float) -> float:
    rr = 1.0 / rr if rr < 1 else rr
    return rr + sqrt(rr * (rr - 1.0))


def e_value(ratio: float, ci_bound: float | None = None) -> EValue:
    """E-value for an effect ratio; ``ci_bound`` is the CI limit closest to 1."""
    if ratio <= 0:
        raise ValueError("ratio must be positive")
    point = _ev(ratio)
    ci: float | None = None
    if ci_bound is not None:
        if ci_bound <= 0:
            raise ValueError("ci_bound must be positive")
        crosses = (ratio >= 1 and ci_bound <= 1) or (ratio < 1 and ci_bound >= 1)
        ci = 1.0 if crosses else _ev(ci_bound)
    text = (
        "An unmeasured confounder would need to be associated with both treatment and "
        f"outcome by a ratio of at least {point:.2f} each to fully explain away the "
        "observed ratio. Weaker confounding could not; this is a plausibility check, "
        "not proof that no such confounder exists."
    )
    return EValue(ratio, point, ci, text)


def confounder_bound(observed_effect: float, confounder_effect: float) -> ConfounderBound:
    """Subtract an assumed confounder-induced bias (same units) from the effect."""
    adj = observed_effect - confounder_effect
    flips = adj * observed_effect <= 0
    text = (
        f"If an unmeasured confounder contributed {confounder_effect:.3g} to the "
        f"observed {observed_effect:.3g}, the remaining effect would be {adj:.3g}"
        + (", which no longer has the same sign. " if flips else ". ")
        + "This is an illustrative bound under an assumed bias, not evidence either way."
    )
    return ConfounderBound(observed_effect, confounder_effect, adj, flips, text)
