"""GroundTruth: independent causal verification of restoration and carbon-credit claims.

The package is organised as a one-directional pipeline::

    ingestion -> geospatial -> matching -> causal -> uncertainty -> evidence -> reporting

Every stage upstream of ``reporting`` is deterministic and auditable. The
``reporting`` layer is the *only* place where a language model is allowed to
run, and it may only narrate values that already exist inside a verified
:class:`groundtruth.core.evidence.EvidenceBundle`.
"""

from groundtruth.core.evidence import Evidence, EvidenceBundle
from groundtruth.core.provenance import Provenance
from groundtruth.core.types import (
    CausalEffect,
    Confidence,
    DonorMatch,
    ProjectClaim,
    TimeSeries,
    VerificationVerdict,
)

__version__ = "0.2.0"

__all__ = [
    "CausalEffect",
    "Confidence",
    "DonorMatch",
    "Evidence",
    "EvidenceBundle",
    "ProjectClaim",
    "Provenance",
    "TimeSeries",
    "VerificationVerdict",
    "__version__",
]
