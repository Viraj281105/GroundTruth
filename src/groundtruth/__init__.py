"""GroundTruth: independent causal verification of restoration and carbon-credit claims.

The codebase is split into three top-level packages by ownership, with a formal
contract between them:

- :mod:`groundtruth.contracts` — the shared, versioned boundary. Changing it
  requires both owners to agree.
- :mod:`groundtruth.engine` — the analytical engine (Viraj). A reproducible
  computational module: ``AnalysisRequest -> AnalysisResult``.
- :mod:`groundtruth.platform` — the application (Bhumi). API, database, jobs,
  dataset services, storage, reporting, deployment.

The platform consumes the engine only through the contract. A test enforces
that, so the split is architectural rather than a convention.

See ``OWNERSHIP.md`` and ``docs/12-contract.md``.
"""

from groundtruth.contracts import (
    CONTRACT_VERSION,
    AnalysisRequest,
    AnalysisResult,
    Evidence,
    EvidenceBundle,
    Provenance,
)

__version__ = "0.3.0"

__all__ = [
    "CONTRACT_VERSION",
    "AnalysisRequest",
    "AnalysisResult",
    "Evidence",
    "EvidenceBundle",
    "Provenance",
    "__version__",
]
