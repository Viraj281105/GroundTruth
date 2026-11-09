"""Biomass-to-carbon conversion layer (requires an explicit, sourced calibration).

GroundTruth enforces 'NDVI is not carbon': a spectral reflectance index cannot
be converted to carbon without a biomass model that has been **calibrated to
field or LiDAR reference data for the ecosystem in question**.

There is deliberately **no default NDVI-to-biomass slope** in this module.
Earlier versions shipped universal per-region slopes (e.g. ``110`` Mg/ha per
unit NDVI) with no citation; the independent audit found them unsupported, and
they were removed. NDVI saturates in closed canopy and is confounded by
herbaceous understory, so a single linear slope is not defensible across sites.

Methodology notes:

* This is a **screening heuristic**, not an IPCC Tier 1/2/3 inventory method.
  IPCC Tier 1 uses ecozone default biomass densities and expansion factors; it
  does not define NDVI-to-biomass slopes. The carbon fraction (0.47) and the
  44/12 stoichiometric ratio are the only generic constants here; the
  root-to-shoot ratio is ecosystem-specific and must be supplied by the
  calibration.
* Biomass (Mg dry matter/ha) -> carbon stock (Mg C/ha) -> CO2-equivalent
  (tCO2e/ha) are distinct quantities and are kept distinct below.
* The reported interval is a **one-sigma (~68%) interval under an assumed
  relative error**. It is not a 95% confidence interval and does not cover
  project area, carbon fraction, root-to-shoot or indicator-estimation error.

If no calibration is supplied, conversion raises :class:`NotCalibratedError`
and the pipeline reports INCONCLUSIVE / NOT CALIBRATED.
"""

from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from groundtruth.contracts.types import Confidence, VerdictLabel

ONE_SIGMA_LEVEL = 0.6827
"""Nominal coverage of a +/-1 sigma interval under a Gaussian assumption."""

ASSUMED_ONE_SIGMA_KIND = "assumed-1sigma-interval"
"""``Confidence.kind`` for intervals built as estimate +/- 1 sigma of an assumed error."""

NOT_CALIBRATED = "NOT CALIBRATED"


class NotCalibratedError(ValueError):
    """Raised when a carbon conversion is requested without a sourced calibration."""


class BiomassParameters(BaseModel):
    """Biomass-model parameters. Calibration fields have **no defaults** on purpose.

    - ``cf``: carbon fraction of dry matter (IPCC 2006 generic default 0.47).
    - ``co2_to_c_ratio``: molecular weight ratio CO2/C (44/12).
    - ``ndvi_to_agb_slope``: Mg dry matter/ha per unit NDVI, **site-calibrated**.
    - ``root_to_shoot_ratio``: belowground/aboveground ratio, ecosystem-specific.
    - ``allometry_relative_error``: assumed 1-sigma relative error of the model.
    - ``calibration_source``: citation / dataset the three calibrated values come from.
    - ``calibration_is_test_fixture``: True for values that exist only to exercise code.
    """

    model_config = ConfigDict(frozen=True)

    region_type: str = Field(
        default="unspecified",
        description="Ecoregion classification this calibration applies to.",
    )
    cf: float = Field(default=0.47, gt=0.0, le=1.0, description="Carbon fraction of dry matter")
    co2_to_c_ratio: float = Field(
        default=44.0 / 12.0, gt=0.0, description="Stoichiometric ratio of CO2 to carbon (44/12)"
    )
    ndvi_to_agb_slope: float | None = Field(
        default=None, gt=0.0, description="Mg dry matter/ha per unit NDVI; None = NOT CALIBRATED"
    )
    root_to_shoot_ratio: float | None = Field(
        default=None, ge=0.0, description="Belowground/aboveground biomass; None = NOT CALIBRATED"
    )
    allometry_relative_error: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Assumed 1-sigma relative error of the model"
    )
    calibration_source: str | None = Field(
        default=None, description="Citation or dataset the calibration derives from"
    )
    calibration_is_test_fixture: bool = Field(
        default=False, description="True if the values are test-only and have no field basis"
    )

    def missing_calibration(self) -> list[str]:
        """Names of required calibration inputs that are absent."""
        missing = [
            name
            for name in ("ndvi_to_agb_slope", "root_to_shoot_ratio", "allometry_relative_error")
            if getattr(self, name) is None
        ]
        if not (self.calibration_source and self.calibration_source.strip()):
            missing.append("calibration_source")
        return missing

    @property
    def is_calibrated(self) -> bool:
        """True only when every calibration input and its source are present."""
        return not self.missing_calibration()


DEFAULT_BIOMASS_PARAMETERS: dict[str, BiomassParameters] = {
    key: BiomassParameters(region_type=key)
    for key in ("miombo", "tropical_dry_forest", "mangrove", "moist_tropical")
}
"""Region templates. All are **uncalibrated**: they carry no slope, ratio or error."""


def get_biomass_parameters(region_type: str = "miombo", **overrides: Any) -> BiomassParameters:
    """Return BiomassParameters for a region, applying overrides.

    Without overrides supplying a calibration the result is NOT CALIBRATED.
    """
    base = DEFAULT_BIOMASS_PARAMETERS.get(region_type.lower())
    data = base.model_dump() if base is not None else {"region_type": region_type}
    data.update(overrides)
    return BiomassParameters(**data)


class CarbonEstimate(BaseModel):
    """Carbon estimate conditional on a stated calibration, with a one-sigma interval."""

    model_config = ConfigDict(frozen=True)

    delta_agb_t_per_ha: float = Field(
        description="Change in above-ground biomass density (Mg dry matter/ha)"
    )
    delta_total_biomass_t_per_ha: float = Field(
        default=0.0, description="Change in above+below-ground biomass (Mg dry matter/ha)"
    )
    delta_carbon_t_per_ha: float = Field(
        default=0.0, description="Change in carbon stock density (Mg C/ha)"
    )
    delta_tco2e_per_ha: float = Field(description="Change in CO2-equivalent density (tCO2e/ha)")
    cumulative_tco2e: float = Field(
        description="Estimated cumulative CO2e stock change over the area (tCO2e)"
    )
    uncertainty_lower_tco2e: float = Field(description="Lower end of the one-sigma interval")
    uncertainty_upper_tco2e: float = Field(description="Upper end of the one-sigma interval")
    std_error_tco2e: float = Field(description="Assumed one-sigma uncertainty (tCO2e)")
    interval_level: float = Field(default=ONE_SIGMA_LEVEL, description="Nominal coverage (~68%)")
    interval_kind: str = Field(default=ASSUMED_ONE_SIGMA_KIND)
    params: BiomassParameters | None = Field(default=None)
    area_ha: float | None = Field(default=None, description="Area in hectares")
    delta_indicator: float | None = Field(default=None, description="Input indicator delta")

    def envelope(self) -> Confidence:
        """Return the interval as a Confidence labelled one-sigma (NOT a 95% interval)."""
        return Confidence(
            lower=float(self.uncertainty_lower_tco2e),
            upper=float(self.uncertainty_upper_tco2e),
            level=self.interval_level,
            kind=self.interval_kind,
        )

    def analytic_95_ci(self) -> Confidence:
        """Return a 95% Gaussian interval (estimate +/- 1.96 * sigma) as a Confidence."""
        half_width = 1.96 * float(self.std_error_tco2e)
        lower = min(self.cumulative_tco2e - half_width, self.cumulative_tco2e + half_width)
        upper = max(self.cumulative_tco2e - half_width, self.cumulative_tco2e + half_width)
        return Confidence(
            lower=float(lower),
            upper=float(upper),
            level=0.95,
            kind="analytic",
        )


class ClaimComparison(BaseModel):
    """Comparison between a developer's claimed credits and an independent carbon estimate."""

    model_config = ConfigDict(frozen=True)

    claimed_tco2e: float = Field(description="Developer claimed credits (tCO2e)")
    estimated_tco2e: float = Field(description="Independent point estimate (tCO2e)")
    lower_tco2e: float = Field(description="Lower bound of independent estimate (tCO2e)")
    upper_tco2e: float = Field(description="Upper bound of independent estimate (tCO2e)")
    over_issuance_share: float = Field(
        description="Over-issuance share: (claimed - estimated) / claimed"
    )
    over_issuance_range: tuple[float, float] = Field(
        description="One-sigma range of over-issuance share (lower_bound, upper_bound)"
    )
    over_issuance_tco2e: float = Field(
        description="Estimated excess credits: claimed - estimated (tCO2e)"
    )
    divergence_ratio: float = Field(
        description="Independent estimate / claimed: estimated / claimed"
    )
    is_over_issued: bool = Field(
        description="True if estimated credits are less than claimed credits"
    )
    verdict_label: VerdictLabel = Field(
        description="Screening verdict label (DIVERGENT_FROM_CLAIM or CONSISTENT_WITH_CLAIM)"
    )

    def envelope(self) -> Confidence:
        """Return the over-issuance share range as a one-sigma interval (NOT a 95% CI)."""
        return Confidence(
            lower=float(self.over_issuance_range[0]),
            upper=float(self.over_issuance_range[1]),
            level=ONE_SIGMA_LEVEL,
            kind=ASSUMED_ONE_SIGMA_KIND,
        )


def convert_indicator_to_carbon(
    delta_indicator: float,
    area_ha: float,
    params: BiomassParameters,
    *,
    indicator_std_error: float = 0.0,
) -> CarbonEstimate:
    """Convert an indicator change to carbon using an explicit, sourced calibration.

    Steps (each quantity is distinct):
        1. delta_agb          [Mg dm/ha]  = delta_indicator * slope
        2. delta_total_biomass[Mg dm/ha]  = delta_agb * (1 + root_to_shoot)
        3. delta_carbon       [Mg C/ha]   = delta_total_biomass * cf
        4. delta_tco2e        [tCO2e/ha]  = delta_carbon * 44/12
        5. cumulative_tco2e   [tCO2e]     = delta_tco2e * area_ha
        6. one-sigma interval from cv_total = sqrt(allometry_rel_error^2 + cv_indicator^2)

    Raises:
        NotCalibratedError: if ``params`` lacks any calibration input or its source.
        ValueError: if ``area_ha`` is not positive.
    """
    if not params.is_calibrated:
        raise NotCalibratedError(
            f"{NOT_CALIBRATED}: biomass parameters for region '{params.region_type}' are missing "
            f"{', '.join(params.missing_calibration())}. NDVI is not carbon; supply a "
            "site-calibrated, sourced biomass model."
        )
    if area_ha <= 0.0:
        raise ValueError(f"area_ha must be positive, got {area_ha}")
    assert params.ndvi_to_agb_slope is not None
    assert params.root_to_shoot_ratio is not None
    assert params.allometry_relative_error is not None

    delta_agb = float(delta_indicator * params.ndvi_to_agb_slope)
    delta_total_biomass = float(delta_agb * (1.0 + params.root_to_shoot_ratio))
    delta_carbon = float(delta_total_biomass * params.cf)
    delta_tco2e_per_ha = float(delta_carbon * params.co2_to_c_ratio)
    cumulative_tco2e = float(delta_tco2e_per_ha * area_ha)

    rel_err_allo = params.allometry_relative_error
    if indicator_std_error > 0.0 and abs(delta_indicator) > 1e-12:
        rel_err_ind = indicator_std_error / abs(delta_indicator)
        cv_total = float(math.sqrt(rel_err_allo**2 + rel_err_ind**2))
    else:
        cv_total = float(rel_err_allo)

    sigma = float(abs(cumulative_tco2e) * cv_total)
    lower = min(cumulative_tco2e - sigma, cumulative_tco2e + sigma)
    upper = max(cumulative_tco2e - sigma, cumulative_tco2e + sigma)

    return CarbonEstimate(
        delta_agb_t_per_ha=delta_agb,
        delta_total_biomass_t_per_ha=delta_total_biomass,
        delta_carbon_t_per_ha=delta_carbon,
        delta_tco2e_per_ha=delta_tco2e_per_ha,
        cumulative_tco2e=cumulative_tco2e,
        uncertainty_lower_tco2e=lower,
        uncertainty_upper_tco2e=upper,
        std_error_tco2e=sigma,
        params=params,
        area_ha=float(area_ha),
        delta_indicator=float(delta_indicator),
    )


def convert_agb_to_carbon(
    delta_agb_t_per_ha: float,
    area_ha: float,
    root_to_shoot_ratio: float | None = None,
    *,
    cf: float = 0.47,
    co2_to_c_ratio: float = 44.0 / 12.0,
    calibration_source: str | None = None,
    agb_std_error_t_per_ha: float = 0.0,
    root_to_shoot_se: float = 0.0,
    cf_se: float = 0.0,
    area_se_ha: float = 0.0,
    params: BiomassParameters | None = None,
) -> CarbonEstimate:
    """Convert a directly validated AGB density change (e.g. LiDAR/field plots) to carbon.

    Steps (each physical quantity is distinct):
        1. delta_agb_t_per_ha           [Mg dm/ha]
        2. delta_total_biomass_t_per_ha [Mg dm/ha] = delta_agb_t_per_ha * (1 + root_to_shoot_ratio)
        3. delta_carbon_t_per_ha        [Mg C/ha]  = delta_total_biomass_t_per_ha * cf
        4. delta_tco2e_per_ha           [tCO2e/ha] = delta_carbon_t_per_ha * co2_to_c_ratio
        5. cumulative_tco2e             [tCO2e]    = delta_tco2e_per_ha * area_ha

    First-order relative uncertainty is propagated in quadrature across all four
    independent components: AGB density change, (1 + root_to_shoot_ratio), carbon
    fraction (cf), and project area (area_ha).

    Raises:
        NotCalibratedError: if ``root_to_shoot_ratio`` is None or ``calibration_source``
            is missing/blank.
        ValueError: if ``area_ha <= 0``, ``root_to_shoot_ratio < 0``, ``cf`` not in (0, 1],
            ``co2_to_c_ratio <= 0``, or any standard error is negative.
    """
    if params is not None:
        if root_to_shoot_ratio is None:
            root_to_shoot_ratio = params.root_to_shoot_ratio
        if calibration_source is None:
            calibration_source = params.calibration_source
        if cf == 0.47 and params.cf != 0.47:
            cf = params.cf
        if co2_to_c_ratio == 44.0 / 12.0 and params.co2_to_c_ratio != 44.0 / 12.0:
            co2_to_c_ratio = params.co2_to_c_ratio

    if root_to_shoot_ratio is None or not (calibration_source and calibration_source.strip()):
        missing: list[str] = []
        if root_to_shoot_ratio is None:
            missing.append("root_to_shoot_ratio")
        if not (calibration_source and calibration_source.strip()):
            missing.append("calibration_source")
        raise NotCalibratedError(
            f"{NOT_CALIBRATED}: direct AGB-to-carbon conversion requires {', '.join(missing)}."
        )

    if area_ha <= 0.0:
        raise ValueError(f"area_ha must be positive, got {area_ha}")
    if root_to_shoot_ratio < 0.0:
        raise ValueError(f"root_to_shoot_ratio must be non-negative, got {root_to_shoot_ratio}")
    if not (0.0 < cf <= 1.0):
        raise ValueError(f"cf must be in (0, 1], got {cf}")
    if co2_to_c_ratio <= 0.0:
        raise ValueError(f"co2_to_c_ratio must be positive, got {co2_to_c_ratio}")
    for name, se_val in (
        ("agb_std_error_t_per_ha", agb_std_error_t_per_ha),
        ("root_to_shoot_se", root_to_shoot_se),
        ("cf_se", cf_se),
        ("area_se_ha", area_se_ha),
    ):
        if se_val < 0.0:
            raise ValueError(f"{name} must be non-negative, got {se_val}")

    delta_agb = float(delta_agb_t_per_ha)
    expansion = 1.0 + float(root_to_shoot_ratio)
    delta_total_biomass = float(delta_agb * expansion)
    delta_carbon = float(delta_total_biomass * cf)
    delta_tco2e_per_ha = float(delta_carbon * co2_to_c_ratio)
    cumulative_tco2e = float(delta_tco2e_per_ha * area_ha)

    rel_rts = float(root_to_shoot_se) / expansion
    rel_cf = float(cf_se) / float(cf)
    rel_area = float(area_se_ha) / float(area_ha)
    if abs(delta_agb) > 1e-12:
        rel_agb = float(agb_std_error_t_per_ha) / abs(delta_agb)
        cv_total = math.sqrt(rel_agb**2 + rel_rts**2 + rel_cf**2 + rel_area**2)
        sigma = float(abs(cumulative_tco2e) * cv_total)
    else:
        sigma = float(agb_std_error_t_per_ha * expansion * cf * co2_to_c_ratio * area_ha)

    lower = min(cumulative_tco2e - sigma, cumulative_tco2e + sigma)
    upper = max(cumulative_tco2e - sigma, cumulative_tco2e + sigma)

    effective_params = params or BiomassParameters(
        cf=cf,
        co2_to_c_ratio=co2_to_c_ratio,
        root_to_shoot_ratio=root_to_shoot_ratio,
        calibration_source=calibration_source,
    )

    return CarbonEstimate(
        delta_agb_t_per_ha=delta_agb,
        delta_total_biomass_t_per_ha=delta_total_biomass,
        delta_carbon_t_per_ha=delta_carbon,
        delta_tco2e_per_ha=delta_tco2e_per_ha,
        cumulative_tco2e=cumulative_tco2e,
        uncertainty_lower_tco2e=lower,
        uncertainty_upper_tco2e=upper,
        std_error_tco2e=sigma,
        params=effective_params,
        area_ha=float(area_ha),
        delta_indicator=None,
    )


def benchmark_against_claim(
    claimed_tco2e: float,
    estimated_tco2e: float,
    lower_tco2e: float,
    upper_tco2e: float,
    *,
    divergence_threshold: float = 0.30,
) -> ClaimComparison:
    """Benchmark developer claimed carbon credits against an independent estimate.

    Computes:
        over_issuance_share = (claimed_tco2e - estimated_tco2e) / claimed_tco2e
        over_issuance_range = (lower_bound, upper_bound)
          where lower_bound corresponds to the highest plausible estimate (conservative):
            (claimed_tco2e - upper_tco2e) / claimed_tco2e
          and upper_bound corresponds to the lowest plausible estimate:
            (claimed_tco2e - lower_tco2e) / claimed_tco2e

    Args:
        claimed_tco2e: Total credits claimed or issued according to the registry.
        estimated_tco2e: Independent point estimate in tCO2e.
        lower_tco2e: Lower bound of the independent carbon estimate uncertainty interval.
        upper_tco2e: Upper bound of the independent carbon estimate uncertainty interval.
        divergence_threshold: Relative divergence threshold for flagging review (default 0.30).

    Returns:
        ClaimComparison object with over-issuance share, range, divergence ratio, and verdict.
    """
    if claimed_tco2e <= 0:
        raise ValueError(f"claimed_tco2e must be positive, got {claimed_tco2e}")
    if lower_tco2e > upper_tco2e:
        raise ValueError(f"lower_tco2e ({lower_tco2e}) cannot exceed upper_tco2e ({upper_tco2e})")

    over_issuance_share = float((claimed_tco2e - estimated_tco2e) / claimed_tco2e)
    b1 = float((claimed_tco2e - upper_tco2e) / claimed_tco2e)
    b2 = float((claimed_tco2e - lower_tco2e) / claimed_tco2e)
    over_issuance_range = (min(b1, b2), max(b1, b2))

    over_issuance_tco2e = float(claimed_tco2e - estimated_tco2e)
    divergence_ratio = float(estimated_tco2e / claimed_tco2e)

    if abs(divergence_ratio - 1.0) <= divergence_threshold:
        verdict_label = VerdictLabel.CONSISTENT_WITH_CLAIM
    else:
        verdict_label = VerdictLabel.DIVERGENT_FROM_CLAIM

    return ClaimComparison(
        claimed_tco2e=float(claimed_tco2e),
        estimated_tco2e=float(estimated_tco2e),
        lower_tco2e=float(lower_tco2e),
        upper_tco2e=float(upper_tco2e),
        over_issuance_share=over_issuance_share,
        over_issuance_range=over_issuance_range,
        over_issuance_tco2e=over_issuance_tco2e,
        divergence_ratio=divergence_ratio,
        is_over_issued=over_issuance_share > 0.0,
        verdict_label=verdict_label,
    )
