"""Covariate engineering: which covariates matter and on what scale.

**Owner: Viraj.** Pure transforms over per-unit scalars. The values themselves
arrive through the ``CovariateAccess`` port; nothing here fetches anything.

Not yet applied inside ``run_analysis``. Matching on a transformed scale changes
which donors are admitted, and the donor table must keep showing raw values in
their own units. Both are part of the donor-pool methodology (#3).
"""

from groundtruth.engine.features.transforms import (
    COVARIATE_TRANSFORMS,
    IDENTITY,
    LOG1P,
    EngineeredCovariates,
    TransformRecord,
    engineer_covariates,
    log1p,
    standardise,
    winsorise,
)

__all__ = [
    "COVARIATE_TRANSFORMS",
    "IDENTITY",
    "LOG1P",
    "EngineeredCovariates",
    "TransformRecord",
    "engineer_covariates",
    "log1p",
    "standardise",
    "winsorise",
]
