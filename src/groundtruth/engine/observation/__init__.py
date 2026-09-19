"""Remote-sensing methodology: indices, quality masking, zonal reduction.

**Owner: Viraj.** These are the decisions about *what to measure and how* —
which index responds to the thing being screened, which pixels are usable,
how a year is reduced to one number, and how much of a zone survived masking.

The plumbing that actually fetches imagery lives in ``groundtruth.platform``
behind the ``ObservationAccess`` port. Methodology here; credentials, retries
and caching there.
"""

from groundtruth.engine.observation.indices import evi, nbr, ndvi, savi
from groundtruth.engine.observation.masking import (
    SCL_INVALID_CLASSES,
    MaskingReport,
    apply_mask,
    audit_masking,
    composite_median,
    scl_cloud_mask,
    valid_observation_counts,
)
from groundtruth.engine.observation.zonal import (
    ZonalStats,
    apply_edge_buffer_note,
    leakage_belt_note,
    zonal_stats,
)

__all__ = [
    "SCL_INVALID_CLASSES",
    "MaskingReport",
    "ZonalStats",
    "apply_edge_buffer_note",
    "apply_mask",
    "audit_masking",
    "composite_median",
    "evi",
    "leakage_belt_note",
    "nbr",
    "ndvi",
    "savi",
    "scl_cloud_mask",
    "valid_observation_counts",
    "zonal_stats",
]
