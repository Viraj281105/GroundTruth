"""ADR-011 as data: the fixed thresholds, the ladder, and the open parameters.

Every number in :class:`Adr011Thresholds` is quoted from
``docs/decisions/ADR-011-unit-of-analysis.md``. Nothing here may be tuned after
a candidate count has been seen — that is the whole point of the ADR, and the
reason these live in a frozen dataclass rather than in a config file or a
function signature default.

The second half of this module is the part people get wrong. ADR-011 fixes the
*rules* but deliberately leaves a short list of *operational* parameters open —
the projection, the raster scale, the literal ecoregion names, the dataset
release strings — because they are implementation choices that could not be
settled in a document without inventing values. ADR-011 calls that list a gate:
while it has entries, the unit set is not reproducible and the pre-registered
run may not start. :class:`RunParameters` is that gate in code. It has no
defaults. A caller that cannot supply a value does not get a guessed one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

ADR = "ADR-011"
"""The decision record this module implements."""


@dataclass(frozen=True, slots=True)
class Adr011Thresholds:
    """The thresholds ADR-011 fixes. Not configurable, by design.

    Attributes are quoted from the ADR's "Eligibility and exclusion rules" and
    "Geometry operation parameters" tables. They are defaults here only so that
    the class can be constructed without arguments; overriding one is a
    departure from the pre-registered specification and callers that do so are
    expected to say why in the unit-set manifest.
    """

    treecover_2000_min_percent: float = 30.0
    """Hansen ``treecover2000`` threshold for the baseline-forest mask."""

    water_occurrence_min_percent: float = 90.0
    """JRC GSW ``occurrence`` threshold, full record, applied uniformly."""

    wdpa_status_year_max: int = 2000
    """Protected areas designated in or before this year are subtracted."""

    wdpa_subtract_unknown_status_year: bool = True
    """``STATUS_YR = 0`` means unknown; ADR-011 subtracts those, conservatively."""

    wdpa_status_values: tuple[str, ...] = (
        "Designated",
        "Inscribed",
        "Established",
    )
    """Only these count as an intervention. ``Proposed`` and ``Not Reported`` do not."""

    ecoregion_min_forest_share: float = 0.50
    """Share of a district's baseline-forest area that must fall in a target ecoregion."""

    area_band_lower: float = 1.0 / 3.0
    """Lower bound of the eligible-area band, as a multiple of the project's eligible area."""

    area_band_upper: float = 3.0
    """Upper bound of the eligible-area band."""

    min_eligible_area_km2: float = 500.0
    """Absolute floor on eligible area, below which a zonal mean is composition-driven."""

    inward_buffer_m: float = 300.0
    """Applied last, to the masked geometry, including mask-induced edges."""

    leakage_belt_km: float = 10.0
    """Outward buffer of the *unmasked* registry boundary."""

    def area_band_km2(self, project_eligible_area_km2: float) -> tuple[float, float]:
        """The admissible eligible-area range for a candidate.

        Args:
            project_eligible_area_km2: The treated unit's eligible area, measured
                after the full mask. ADR-011 is explicit that the band is derived
                from the eligible area and not from the registered area.

        Returns:
            The inclusive ``(lower, upper)`` bounds in km².

        Raises:
            ValueError: if the project's eligible area is not positive. A band
                derived from a missing measurement would silently admit
                everything.
        """
        if project_eligible_area_km2 <= 0:
            raise ValueError(
                "the area band is derived from the project's measured eligible area; "
                f"got {project_eligible_area_km2!r}"
            )
        return (
            self.area_band_lower * project_eligible_area_km2,
            self.area_band_upper * project_eligible_area_km2,
        )


@dataclass(frozen=True, slots=True)
class Rung:
    """One rung of the fixed three-rung search-region ladder."""

    number: int
    description: str
    countries: tuple[str, ...]
    """ISO3 codes, as they appear in the administrative partition."""

    ecoregion_key: str
    """Key into :attr:`RunParameters.ecoregion_names`; resolved to literal names."""


LADDER: Final[tuple[Rung, ...]] = (
    Rung(
        number=1,
        description="Southern Miombo + Central Zambezian Miombo woodlands, in ZWE, ZMB, MOZ",
        countries=("ZWE", "ZMB", "MOZ"),
        ecoregion_key="rung1",
    ),
    Rung(
        number=2,
        description="Rung 1 + Eastern Miombo woodlands + Zambezian-Mopane woodlands",
        countries=("ZWE", "ZMB", "MOZ"),
        ecoregion_key="rung2",
    ),
    Rung(
        number=3,
        description="Rung 2 + the same ecoregions in MWI and TZA",
        countries=("ZWE", "ZMB", "MOZ", "MWI", "TZA"),
        ecoregion_key="rung3",
    ),
)
"""The ladder, fixed in advance. Order is the climb order and is not negotiable."""

ADMINISTRATIVE_ASSET: Final[str] = "FAO/GAUL/2015/level2"
ECOREGION_ASSET: Final[str] = "RESOLVE/ECOREGIONS/2017"
BASELINE_FOREST_ASSET: Final[str] = "UMD/hansen/global_forest_change_2023_v1_11"
BASELINE_FOREST_BAND: Final[str] = "treecover2000"
PERMANENT_WATER_ASSET: Final[str] = "JRC/GSW1_4/GlobalSurfaceWater"
PERMANENT_WATER_BAND: Final[str] = "occurrence"
PROTECTED_AREA_ASSET: Final[str] = "WCMC/WDPA/current/polygons"

UNIT_ID_PREFIX: Final[str] = "gaul2015"
"""``unit_id`` is ``gaul2015:{ADM2_CODE}`` until #60 gives units real descriptors."""


class MissingRunParameterError(ValueError):
    """A parameter ADR-011 leaves open was not supplied.

    Raised instead of defaulting. ADR-011's "Geometry operation parameters"
    table is a gate on the run: a guessed projection or a guessed raster scale
    produces a unit set that nobody can reproduce, and it produces it silently.
    """


@dataclass(frozen=True, slots=True)
class RunParameters:
    """The parameters ADR-011 leaves open, which must be fixed before a run.

    All of these change the resulting pool at the margin, none of them is a
    scientific choice, and every one of them must be committed **before any
    candidate count is seen**. Setting one afterwards is a protocol violation,
    not a tuning step.

    There are no defaults. :meth:`validate` refuses an incomplete set rather
    than filling gaps.
    """

    projection: str
    """Equal-area CRS for every buffer and area computation, e.g. an EPSG code."""

    raster_scale_m: float
    """Scale at which raster masks are evaluated."""

    raster_reducer: str
    """How raster values are reduced to the mask, e.g. ``"mean"`` or ``"mode"``."""

    simplification_max_error_m: float
    """Geometry simplification tolerance. Changes computed areas; must be recorded."""

    ecoregion_names: dict[str, tuple[str, ...]]
    """Literal ``ECO_NAME`` values per ladder rung key, so rungs are auditable."""

    wdpa_release: str
    """The pinned WDPA monthly release string."""

    carbon_registry_snapshot_date: str
    """ISO date of the pinned registered-projects snapshot."""

    pool_size: int
    """Eligible-candidate target the ladder's stopping rule tests against."""

    min_donors: int
    """Admitted-donor floor. Below this at rung 3 the case is refused."""

    max_donors: int
    """Cap on admitted donors, applied by the matching stage."""

    excluded_carbon_project_districts: tuple[str, ...] = field(default=())
    """Districts excluded whole because a registered project has no geometry.

    Committed before the pool is generated, per ADR-011: deciding after the fact
    that a district "probably contains a project" is exactly the discretion the
    ADR removes.
    """

    def validate(self) -> None:
        """Check the gate.

        Raises:
            MissingRunParameterError: if any parameter is empty, non-positive, or
                missing a ladder rung's ecoregion names.
        """
        problems: list[str] = []
        if not self.projection:
            problems.append("projection")
        if self.raster_scale_m <= 0:
            problems.append("raster_scale_m")
        if not self.raster_reducer:
            problems.append("raster_reducer")
        if self.simplification_max_error_m < 0:
            problems.append("simplification_max_error_m")
        if not self.wdpa_release:
            problems.append("wdpa_release")
        if not self.carbon_registry_snapshot_date:
            problems.append("carbon_registry_snapshot_date")
        if self.pool_size <= 0:
            problems.append("pool_size")
        if self.min_donors <= 0:
            problems.append("min_donors")
        if self.max_donors < self.min_donors:
            problems.append("max_donors (must be >= min_donors)")
        for rung in LADDER:
            names = self.ecoregion_names.get(rung.ecoregion_key)
            if not names:
                problems.append(f"ecoregion_names[{rung.ecoregion_key!r}]")
        if problems:
            raise MissingRunParameterError(
                "ADR-011 leaves these parameters open and they must be fixed and committed "
                "before any candidate count is seen: " + ", ".join(problems)
            )

    def ecoregions_for(self, rung: Rung) -> tuple[str, ...]:
        """Literal ecoregion names for one rung.

        Raises:
            MissingRunParameterError: if the rung has no names pinned.
        """
        names = self.ecoregion_names.get(rung.ecoregion_key)
        if not names:
            raise MissingRunParameterError(
                f"no ECO_NAME values pinned for ladder rung {rung.number}; "
                "the ladder is only auditable if rung contents are literal values"
            )
        return names
