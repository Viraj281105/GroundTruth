"""Assessment engine: eight dimensions, levels 0-5, layered conclusions, recommendations.

Deterministic and pure: it receives real artifacts already gathered by the platform
(``AssessmentInputs``) and returns an ``Assessment``. No I/O, no platform imports, no LLM.
"""

from groundtruth.engine.assessment.assess import assess
from groundtruth.engine.assessment.types import (
    Assessment,
    AssessmentInputs,
    AttributionResult,
    ClimateYear,
    Conclusion,
    DimensionResult,
    ReadinessSummary,
    Recommendation,
    SeriesPoint,
    SpreadPoint,
)

__all__ = [
    "Assessment",
    "AssessmentInputs",
    "AttributionResult",
    "ClimateYear",
    "Conclusion",
    "DimensionResult",
    "ReadinessSummary",
    "Recommendation",
    "SeriesPoint",
    "SpreadPoint",
    "assess",
]
