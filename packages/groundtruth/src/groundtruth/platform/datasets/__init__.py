"""Dataset services: registry, pinning, credentials, caching, and the
DataAccess implementations the engine runs against.

**Owner: Bhumi.**
"""

from groundtruth.platform.datasets.access import (
    PLANETARY_COMPUTER_S2_DATASET,
    SYNTHETIC_KARIBA_FIXTURE_DATASET,
    StacCachedObservationAccess,
    SyntheticCovariateAccess,
    SyntheticDonorAccess,
    SyntheticFixtureCovariateAccess,
    SyntheticFixtureDonorAccess,
    SyntheticFixtureObservationAccess,
    SyntheticObservationAccess,
    earth_engine_access,
    earth_engine_observations,
    real_observation_cases,
    synthetic_access,
    synthetic_fixture_access,
    synthetic_fixture_available,
)
from groundtruth.platform.datasets.evidence_registry import (
    EvidenceRegistry,
    EvidenceSource,
    IngestionMode,
    ModalityType,
    ProcessingStep,
    ProductionAnalysisBlockedError,
    SourceLifecycle,
    ValidationStatus,
    assert_dataset_allowed_for_production,
    get_global_evidence_registry,
)
from groundtruth.platform.datasets.observation import EarthEngineObservationAccess
from groundtruth.platform.datasets.synthetic import SYNTHETIC_MARKER, is_synthetic

__all__ = [
    "PLANETARY_COMPUTER_S2_DATASET",
    "SYNTHETIC_KARIBA_FIXTURE_DATASET",
    "SYNTHETIC_MARKER",
    "EarthEngineObservationAccess",
    "EvidenceRegistry",
    "EvidenceSource",
    "IngestionMode",
    "ModalityType",
    "ProcessingStep",
    "ProductionAnalysisBlockedError",
    "SourceLifecycle",
    "StacCachedObservationAccess",
    "SyntheticCovariateAccess",
    "SyntheticDonorAccess",
    "SyntheticFixtureCovariateAccess",
    "SyntheticFixtureDonorAccess",
    "SyntheticFixtureObservationAccess",
    "SyntheticObservationAccess",
    "ValidationStatus",
    "assert_dataset_allowed_for_production",
    "earth_engine_access",
    "earth_engine_observations",
    "get_global_evidence_registry",
    "is_synthetic",
    "real_observation_cases",
    "synthetic_access",
    "synthetic_fixture_access",
    "synthetic_fixture_available",
]
