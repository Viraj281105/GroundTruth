"""The GroundTruth analytical engine.

    AnalysisRequest  ->  run_analysis  ->  AnalysisResult

**Owner: Viraj.** This package holds the scientific core: remote-sensing
methodology, feature engineering, donor-pool construction, causal estimation,
placebo inference, uncertainty quantification and evidence assembly.

The platform imports exactly three names from here — ``run_analysis``,
``describe_engine`` and ``ENGINE_VERSION``. Everything below this module is
private to the engine and may be restructured freely. A test enforces that
rule, so the boundary is real rather than a convention.
"""

from groundtruth.engine.run import (
    ENGINE_VERSION,
    describe_engine,
    engine_ref,
    run_analysis,
)

__all__ = ["ENGINE_VERSION", "describe_engine", "engine_ref", "run_analysis"]
