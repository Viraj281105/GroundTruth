"""Causal estimators: synthetic control (primary) and difference-in-differences (cross-check)."""

from groundtruth.causal.did import DiDResult, estimate_did
from groundtruth.causal.synthetic_control import (
    SyntheticControlFit,
    fit_synthetic_control,
    solve_simplex_least_squares,
)

__all__ = [
    "DiDResult",
    "SyntheticControlFit",
    "estimate_did",
    "fit_synthetic_control",
    "solve_simplex_least_squares",
]
