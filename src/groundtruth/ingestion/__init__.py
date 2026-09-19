"""Data ingestion: provider interfaces and concrete Earth-observation backends."""

from groundtruth.ingestion.base import (
    AreaOfInterest,
    ClaimProvider,
    CovariateProvider,
    DonorPoolProvider,
    ObservationProvider,
    ObservationRequest,
)
from groundtruth.ingestion.synthetic import (
    SYNTHETIC_MARKER,
    SyntheticCovariateProvider,
    SyntheticDonorPoolProvider,
    SyntheticObservationProvider,
    is_synthetic,
)

__all__ = [
    "SYNTHETIC_MARKER",
    "AreaOfInterest",
    "ClaimProvider",
    "CovariateProvider",
    "DonorPoolProvider",
    "ObservationProvider",
    "ObservationRequest",
    "SyntheticCovariateProvider",
    "SyntheticDonorPoolProvider",
    "SyntheticObservationProvider",
    "is_synthetic",
]
