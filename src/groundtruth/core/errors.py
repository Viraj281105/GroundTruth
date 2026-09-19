"""Exception hierarchy for GroundTruth.

Errors are deliberately specific: a failure in the analytical engine must never
be silently converted into a weaker claim in the report.
"""


class GroundTruthError(Exception):
    """Base class for all GroundTruth errors."""


class ConfigurationError(GroundTruthError):
    """Raised when configuration or credentials are missing or invalid."""


class CaseDefinitionError(GroundTruthError):
    """Raised when a case definition file is missing, malformed or inconsistent."""


class DataUnavailableError(GroundTruthError):
    """Raised when a required Earth-observation product cannot be retrieved."""


class InsufficientDataError(GroundTruthError):
    """Raised when data exists but is too sparse to support an estimate.

    Preferring this over a low-confidence number is a core design rule: an
    honest refusal is more useful to a due-diligence team than a fragile point
    estimate.
    """


class DonorPoolError(GroundTruthError):
    """Raised when no admissible donor pool can be constructed."""


class EstimationError(GroundTruthError):
    """Raised when a causal estimator fails to converge or is mis-specified."""


class ProvenanceError(GroundTruthError):
    """Raised when an evidence item is missing required provenance."""


class GroundingViolationError(GroundTruthError):
    """Raised when generated narrative text contains unverifiable claims.

    This is the hard boundary between the analytical engine and the GenAI
    layer. If narration asserts a number or a causal/legal conclusion that is
    not present in the evidence bundle, the report is rejected rather than
    published with a disclaimer.
    """
