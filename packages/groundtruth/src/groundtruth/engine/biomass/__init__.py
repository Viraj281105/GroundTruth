"""Biomass and carbon allometry layer.

GroundTruth enforces 'NDVI is not carbon': a spectral index cannot be
converted to carbon without an explicit, sourced, site-calibrated biomass model.
No default slopes are shipped; uncalibrated parameters yield NOT CALIBRATED.
"""

from groundtruth.engine.biomass.allometry import (
    DEFAULT_BIOMASS_PARAMETERS,
    BiomassParameters,
    CarbonEstimate,
    ClaimComparison,
    NotCalibratedError,
    benchmark_against_claim,
    convert_agb_to_carbon,
    convert_indicator_to_carbon,
    get_biomass_parameters,
)

__all__ = [
    "DEFAULT_BIOMASS_PARAMETERS",
    "BiomassParameters",
    "CarbonEstimate",
    "ClaimComparison",
    "NotCalibratedError",
    "benchmark_against_claim",
    "convert_agb_to_carbon",
    "convert_indicator_to_carbon",
    "get_biomass_parameters",
]
