"""Causal estimators: synthetic control (primary) and difference-in-differences (cross-check)."""

from groundtruth.engine.causal.climate_confounding import (
    ClimateConfoundingReport,
    ClimateSpecDiagnostic,
    DonorClimateComparability,
    DonorPoolClimateDiagnostics,
    Sentinel2ClimateCoMovement,
    analyze_sentinel2_climate_comovement,
    build_climate_covariate_matrices,
    check_post_treatment_covariate_divergence,
    estimate_untreated_climate_sensitivity,
    evaluate_causal_gates_for_spec,
    evaluate_donor_climate_comparability,
    run_climate_confounding_analysis,
)
from groundtruth.engine.causal.did import DiDResult, estimate_did
from groundtruth.engine.causal.synthetic_control import (
    HullDiagnostic,
    SyntheticControlFit,
    convex_hull_diagnostic,
    fit_synthetic_control,
    solve_simplex_least_squares,
)

__all__ = [
    "ClimateConfoundingReport",
    "ClimateSpecDiagnostic",
    "DiDResult",
    "DonorClimateComparability",
    "DonorPoolClimateDiagnostics",
    "HullDiagnostic",
    "Sentinel2ClimateCoMovement",
    "SyntheticControlFit",
    "analyze_sentinel2_climate_comovement",
    "build_climate_covariate_matrices",
    "check_post_treatment_covariate_divergence",
    "convex_hull_diagnostic",
    "estimate_did",
    "estimate_untreated_climate_sensitivity",
    "evaluate_causal_gates_for_spec",
    "evaluate_donor_climate_comparability",
    "fit_synthetic_control",
    "run_climate_confounding_analysis",
    "solve_simplex_least_squares",
]
