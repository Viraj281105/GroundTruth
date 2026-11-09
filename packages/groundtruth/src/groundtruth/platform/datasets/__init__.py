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
from groundtruth.platform.datasets.observation import EarthEngineObservationAccess
from groundtruth.platform.datasets.synthetic import SYNTHETIC_MARKER, is_synthetic

__all__ = [
    "PLANETARY_COMPUTER_S2_DATASET",
    "SYNTHETIC_KARIBA_FIXTURE_DATASET",
    "SYNTHETIC_MARKER",
    "EarthEngineObservationAccess",
    "StacCachedObservationAccess",
    "SyntheticCovariateAccess",
    "SyntheticDonorAccess",
    "SyntheticFixtureCovariateAccess",
    "SyntheticFixtureDonorAccess",
    "SyntheticFixtureObservationAccess",
    "SyntheticObservationAccess",
    "earth_engine_access",
    "earth_engine_observations",
    "is_synthetic",
    "real_observation_cases",
    "synthetic_access",
    "synthetic_fixture_access",
    "synthetic_fixture_available",
]
