"""Donor-pool construction and covariate matching."""

from groundtruth.engine.matching.donors import (
    DEFAULT_COVARIATES,
    SUTVA_SPATIAL_CAVEAT,
    DonorPool,
    DonorSpatialDiagnostic,
    MatchingConfig,
    SpatialDonorAssessment,
    assess_donor_spatial_eligibility,
    match_donors,
    standardised_mean_difference,
    validate_donor_eligibility,
)

__all__ = [
    "DEFAULT_COVARIATES",
    "SUTVA_SPATIAL_CAVEAT",
    "DonorPool",
    "DonorSpatialDiagnostic",
    "MatchingConfig",
    "SpatialDonorAssessment",
    "assess_donor_spatial_eligibility",
    "match_donors",
    "standardised_mean_difference",
    "validate_donor_eligibility",
]
