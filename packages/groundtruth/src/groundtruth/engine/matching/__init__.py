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
from groundtruth.engine.matching.eligibility import (
    DonorCategory,
    DonorEligibilityAssessment,
    DonorMatrixDiagnostics,
    DonorUnitAuditRecord,
    build_kariba_donor_eligibility_matrix,
)

__all__ = [
    "DEFAULT_COVARIATES",
    "SUTVA_SPATIAL_CAVEAT",
    "DonorCategory",
    "DonorEligibilityAssessment",
    "DonorMatrixDiagnostics",
    "DonorPool",
    "DonorSpatialDiagnostic",
    "DonorUnitAuditRecord",
    "MatchingConfig",
    "SpatialDonorAssessment",
    "assess_donor_spatial_eligibility",
    "build_kariba_donor_eligibility_matrix",
    "match_donors",
    "standardised_mean_difference",
    "validate_donor_eligibility",
]
