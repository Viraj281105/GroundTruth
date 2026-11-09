"""The GroundTruth analytical engine.

    AnalysisRequest  ->  run_analysis  ->  AnalysisResult

**Owner: Viraj.** This package holds the scientific core: remote-sensing
methodology, feature engineering, donor-pool construction, causal estimation,
placebo inference, uncertainty quantification and evidence assembly.

The platform imports a fixed set of names from here — ``run_analysis``,
``describe_engine``, ``ENGINE_VERSION`` and, since the assessment engine (spec 6A), ``assess``
with its input/output types. Everything below this module is
private to the engine and may be restructured freely. A test enforces that
rule, so the boundary is real rather than a convention.
"""

# Deliberate public-API addition (spec 6A): the platform's assessment adapter builds
# ``AssessmentInputs`` from real artifacts and calls ``assess``; these are its only seams.
from groundtruth.engine.assessment import (
    Assessment,
    AssessmentInputs,
    ClimateYear,
    ReadinessSummary,
    SeriesPoint,
    SpreadPoint,
    assess,
)
from groundtruth.engine.run import (
    ENGINE_VERSION,
    describe_engine,
    engine_ref,
    run_analysis,
)

__all__ = [
    "ENGINE_VERSION",
    "Assessment",
    "AssessmentInputs",
    "ClimateYear",
    "ReadinessSummary",
    "SeriesPoint",
    "SpreadPoint",
    "assess",
    "describe_engine",
    "engine_ref",
    "run_analysis",
]
