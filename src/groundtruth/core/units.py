"""Unit vocabulary and the guards that keep indicator semantics honest.

The single most common error in satellite-based carbon claims is treating a
greenness index as if it were a stock of carbon. This module makes that error
impossible to commit accidentally: conversions between unit *families* must be
declared explicitly and carry their own provenance.
"""

from __future__ import annotations

from enum import Enum


class UnitFamily(str, Enum):
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


UNIT_FAMILIES: dict[str, UnitFamily] = {
    "ndvi": UnitFamily.INDEX,
    "evi": UnitFamily.INDEX,
    "nbr": UnitFamily.INDEX,
    "ha": UnitFamily.AREA,
    "km2": UnitFamily.AREA,
    "fraction": UnitFamily.FRACTION,
    "percent": UnitFamily.FRACTION,
    "t/ha": UnitFamily.BIOMASS,
    "tC": UnitFamily.CARBON,
    "tCO2e": UnitFamily.CARBON,
    "credits": UnitFamily.COUNT,
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
            f"Unknown unit {unit!r}. Declare it in groundtruth.core.units.UNIT_FAMILIES "
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
            "model (see docs/05-causal-inference.md, 'NDVI is not carbon')."
        )
