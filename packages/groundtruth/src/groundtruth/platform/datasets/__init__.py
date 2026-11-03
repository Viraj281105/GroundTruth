"""Dataset services: registry, pinning, credentials, caching, and the
DataAccess implementations the engine runs against.

**Owner: Bhumi.**
"""

from groundtruth.platform.datasets.access import (
    SyntheticCovariateAccess,
    SyntheticDonorAccess,
    SyntheticObservationAccess,
    earth_engine_access,
    earth_engine_observations,
    synthetic_access,
)
from groundtruth.platform.datasets.observation import EarthEngineObservationAccess
from groundtruth.platform.datasets.synthetic import SYNTHETIC_MARKER, is_synthetic

__all__ = [
    "SYNTHETIC_MARKER",
    "EarthEngineObservationAccess",
    "SyntheticCovariateAccess",
    "SyntheticDonorAccess",
    "SyntheticObservationAccess",
    "earth_engine_access",
    "earth_engine_observations",
    "is_synthetic",
    "synthetic_access",
]
