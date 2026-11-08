"""Unit vocabulary and the guards that keep indicator semantics honest.

The single most common error in satellite-based carbon claims is treating a
greenness index as if it were a stock of carbon. This module makes that error
impossible to commit accidentally: conversions between unit *families* must be
declared explicitly and carry their own provenance.
"""

from __future__ import annotations

from enum import StrEnum


class UnitFamily(StrEnum):
    """Families of quantities that must never be silently interchanged."""

    INDEX = "index"
    """Dimensionless spectral indices (NDVI, EVI, NBR). Not a biophysical stock."""

    AREA = "area"
    """Areal quantities such as hectares of forest cover."""

    FRACTION = "fraction"
    """Bounded fractions such as tree-canopy cover in [0, 1]."""

    BIOMASS = "biomass"
    """Above-ground biomass density, e.g. t/ha."""

    CARBON = "carbon"
    """Carbon or CO2-equivalent stocks and fluxes, e.g. tCO2e."""

    COUNT = "count"
    """Counts, e.g. number of credits issued."""

    PRECIPITATION = "precipitation"
    """Precipitation depths and rates (e.g. mm, mm/year, mm/season, mm/month, m)."""

    TEMPERATURE = "temperature"
    """Thermodynamic or surface air temperatures and anomalies (e.g. degC, K, degC_anomaly)."""

    DROUGHT_INDEX = "drought_index"
    """Standardized drought, water-balance, or variability indices (e.g. spi, spei, z_score, cv, mm_pet)."""


UNIT_FAMILIES: dict[str, UnitFamily] = {
    "ndvi": UnitFamily.INDEX,
    "evi": UnitFamily.INDEX,
    "nbr": UnitFamily.INDEX,
    "ndmi": UnitFamily.INDEX,
    "ha": UnitFamily.AREA,
    "km2": UnitFamily.AREA,
    "fraction": UnitFamily.FRACTION,
    "percent": UnitFamily.FRACTION,
    "share": UnitFamily.FRACTION,
    "t/ha": UnitFamily.BIOMASS,
    "tC": UnitFamily.CARBON,
    "tCO2e": UnitFamily.CARBON,
    "credits": UnitFamily.COUNT,
    "mm": UnitFamily.PRECIPITATION,
    "mm/year": UnitFamily.PRECIPITATION,
    "mm/season": UnitFamily.PRECIPITATION,
    "mm/month": UnitFamily.PRECIPITATION,
    "mm/day": UnitFamily.PRECIPITATION,
    "m": UnitFamily.PRECIPITATION,
    "degC": UnitFamily.TEMPERATURE,
    "K": UnitFamily.TEMPERATURE,
    "degC_anomaly": UnitFamily.TEMPERATURE,
    "spi": UnitFamily.DROUGHT_INDEX,
    "spei": UnitFamily.DROUGHT_INDEX,
    "z_score": UnitFamily.DROUGHT_INDEX,
    "cv": UnitFamily.DROUGHT_INDEX,
    "mm_pet": UnitFamily.DROUGHT_INDEX,
}


def unit_family(unit: str) -> UnitFamily:
    """Return the :class:`UnitFamily` for ``unit``.

    Raises:
        ValueError: if the unit is not part of the declared vocabulary. Unknown
            units are rejected rather than guessed.
    """
    try:
        return UNIT_FAMILIES[unit]
    except KeyError as exc:  # pragma: no cover - trivial branch
        raise ValueError(
            f"Unknown unit {unit!r}. Declare it in groundtruth.contracts.units.UNIT_FAMILIES "
            "before using it in an evidence object."
        ) from exc


def is_carbon_unit(unit: str) -> bool:
    """True if ``unit`` denotes a carbon or CO2-equivalent quantity."""
    return unit in UNIT_FAMILIES and UNIT_FAMILIES[unit] is UnitFamily.CARBON


def assert_not_index_to_carbon(source_unit: str, target_unit: str) -> None:
    """Forbid implicit index -> carbon conversion.

    NDVI is a reflectance ratio; carbon is a mass stock. Any mapping between
    them requires an allometric or biomass model with its own error budget, and
    must be performed by an explicit, provenance-carrying conversion step.

    Raises:
        ValueError: when a spectral index is converted directly to carbon.
    """
    if unit_family(source_unit) is UnitFamily.INDEX and is_carbon_unit(target_unit):
        raise ValueError(
            f"Refusing to convert {source_unit!r} directly to {target_unit!r}: a spectral "
            "index is not a carbon stock. Route the conversion through an explicit biomass "
            "model (see docs/science/causal-inference.md, 'NDVI is not carbon')."
        )


KELVIN_OFFSET: float = 273.15


def kelvin_to_celsius(temp_k: float) -> float:
    """Convert thermodynamic temperature in Kelvin (K) to Celsius (degC)."""
    if temp_k < 0.0:
        raise ValueError(f"Kelvin temperature cannot be negative: {temp_k}")
    return float(temp_k - KELVIN_OFFSET)


def celsius_to_kelvin(temp_c: float) -> float:
    """Convert temperature in Celsius (degC) to Kelvin (K)."""
    if temp_c < -KELVIN_OFFSET:
        raise ValueError(f"Celsius temperature below absolute zero (-273.15 C): {temp_c}")
    return float(temp_c + KELVIN_OFFSET)


def meters_to_mm(depth_m: float) -> float:
    """Convert precipitation depth in meters (ERA5 convention) to millimeters (mm)."""
    if depth_m < 0.0:
        raise ValueError(f"Precipitation depth cannot be negative: {depth_m}")
    return float(depth_m * 1000.0)


def mm_per_day_to_mm_per_month(rate_mm_per_day: float, days_in_month: int) -> float:
    """Convert daily mean precipitation rate (mm/day) to monthly total (mm/month)."""
    if rate_mm_per_day < 0.0:
        raise ValueError(f"Precipitation rate cannot be negative: {rate_mm_per_day}")
    if not (28 <= days_in_month <= 31):
        raise ValueError(f"Invalid days_in_month={days_in_month}; expected 28..31.")
    return float(rate_mm_per_day * days_in_month)


def convert_climate_unit(
    value: float,
    source_unit: str,
    target_unit: str,
    *,
    days_in_month: int | None = None,
) -> float:
    """Explicitly convert a climate quantity between compatible units within the same family.

    Raises:
        ValueError: if units are unknown, belong to different unit families, or if
            the requested conversion is scientifically invalid (e.g. climate -> carbon
            or climate -> spectral index).
    """
    src_family = unit_family(source_unit)
    tgt_family = unit_family(target_unit)
    if src_family != tgt_family:
        raise ValueError(
            f"Refusing cross-family unit conversion from {source_unit!r} ({src_family.value}) "
            f"to {target_unit!r} ({tgt_family.value})."
        )
    if source_unit == target_unit:
        return float(value)

    if (source_unit, target_unit) == ("K", "degC"):
        return kelvin_to_celsius(value)
    if (source_unit, target_unit) == ("degC", "K"):
        return celsius_to_kelvin(value)
    if (source_unit, target_unit) == ("m", "mm"):
        return meters_to_mm(value)
    if (source_unit, target_unit) == ("mm", "m"):
        if value < 0.0:
            raise ValueError(f"Precipitation depth cannot be negative: {value}")
        return float(value / 1000.0)
    if (source_unit, target_unit) == ("mm/day", "mm/month"):
        if days_in_month is None:
            raise ValueError("Converting 'mm/day' to 'mm/month' requires days_in_month.")
        return mm_per_day_to_mm_per_month(value, days_in_month)
    if (source_unit, target_unit) == ("mm/month", "mm/day"):
        if days_in_month is None or not (28 <= days_in_month <= 31):
            raise ValueError(
                "Converting 'mm/month' to 'mm/day' requires valid days_in_month (28..31)."
            )
        if value < 0.0:
            raise ValueError(f"Precipitation cannot be negative: {value}")
        return float(value / days_in_month)

    raise ValueError(
        f"Unsupported intra-family conversion from {source_unit!r} to {target_unit!r}."
    )
