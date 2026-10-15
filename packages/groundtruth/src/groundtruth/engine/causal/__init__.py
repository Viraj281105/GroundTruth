"""Causal estimators: synthetic control (primary) and difference-in-differences (cross-check)."""

from groundtruth.engine.causal.did import DiDResult, estimate_did
from groundtruth.engine.causal.synthetic_control import (
    HullDiagnostic,
    SyntheticControlFit,
    convex_hull_diagnostic,
    fit_synthetic_control,
    solve_simplex_least_squares,
)

__all__ = [
    "DiDResult",
    "HullDiagnostic",
    "SyntheticControlFit",
    "convex_hull_diagnostic",
    "estimate_did",
    "fit_synthetic_control",
    "solve_simplex_least_squares",
]
