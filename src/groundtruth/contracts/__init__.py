"""The contract between the analytical engine and the platform.

This package is the boundary. Everything in it is shared, versioned and frozen:
changing it requires both owners to agree, because both sides depend on it.

    Viraj's engine:   AnalysisRequest  ->  AnalysisResult
    Bhumi's platform: consumes AnalysisResult, implements the DataAccess ports

Nothing here imports from ``groundtruth.engine`` or ``groundtruth.platform``.
That rule is enforced by a test, because a contract that quietly depends on one
side's internals is not a contract.

See ``docs/12-contract.md`` for the full specification and change process.
"""

from groundtruth.contracts.errors import (
    CaseDefinitionError,
    ConfigurationError,
    DataUnavailableError,
    DonorPoolError,
    EstimationError,
    GroundingViolationError,
    GroundTruthError,
    InsufficientDataError,
    ProvenanceError,
)
from groundtruth.contracts.evidence import Evidence, EvidenceBuilder, EvidenceBundle
from groundtruth.contracts.identifiers import (
    DatasetRef,
    EngineRef,
    ModelRef,
    new_run_id,
    spec_hash,
)
from groundtruth.contracts.ports import (
    CovariateAccess,
    DataAccess,
    DonorCandidateAccess,
    ObservationAccess,
    ObservationSpec,
)
from groundtruth.contracts.provenance import Provenance
from groundtruth.contracts.request import (
    AnalysisRequest,
    AnalysisWindow,
    ClaimUnderTest,
    DonorSpec,
    EstimationSpec,
    RobustnessSpec,
    UnitRef,
)
from groundtruth.contracts.result import (
    AnalysisError,
    AnalysisResult,
    AnalysisStatus,
    EngineStatus,
    ErrorCode,
    RunMetrics,
)
from groundtruth.contracts.types import (
    STANDARD_CAVEATS,
    CausalEffect,
    Confidence,
    DonorMatch,
    Indicator,
    MethodologyStandard,
    TimeSeries,
    VerdictLabel,
    VerificationVerdict,
)
from groundtruth.contracts.version import CONTRACT_VERSION, is_compatible

__all__ = [
    "CONTRACT_VERSION",
    "STANDARD_CAVEATS",
    "AnalysisError",
    "AnalysisRequest",
    "AnalysisResult",
    "AnalysisStatus",
    "AnalysisWindow",
    "CaseDefinitionError",
    "CausalEffect",
    "ClaimUnderTest",
    "Confidence",
    "ConfigurationError",
    "CovariateAccess",
    "DataAccess",
    "DataUnavailableError",
    "DatasetRef",
    "DonorCandidateAccess",
    "DonorMatch",
    "DonorPoolError",
    "DonorSpec",
    "EngineRef",
    "EngineStatus",
    "ErrorCode",
    "EstimationError",
    "EstimationSpec",
    "Evidence",
    "EvidenceBuilder",
    "EvidenceBundle",
    "GroundTruthError",
    "GroundingViolationError",
    "Indicator",
    "InsufficientDataError",
    "MethodologyStandard",
    "ModelRef",
    "ObservationAccess",
    "ObservationSpec",
    "Provenance",
    "ProvenanceError",
    "RobustnessSpec",
    "RunMetrics",
    "TimeSeries",
    "UnitRef",
    "VerdictLabel",
    "VerificationVerdict",
    "is_compatible",
    "new_run_id",
    "spec_hash",
]
