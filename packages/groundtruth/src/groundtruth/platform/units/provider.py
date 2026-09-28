"""The masking port, and the Earth Engine implementation that does not exist yet.

ADR-011's eligibility mask is five raster and vector operations over pinned
assets:

``district ∩ target_ecoregions ∩ baseline_forest MINUS permanent_water MINUS
protected_areas MINUS registered_carbon_projects ⊖ inward_buffer(300 m)``

None of that can be done in this package. It needs a geometry engine and the
pinned assets, which is issue #23's work, reached through the Earth Engine
client of #1/#22. This module defines the seam: what the rules layer needs to be
given, and what an implementation must promise.

**Why there is no local fallback.** A provider that returned plausible districts
when the real ones were unavailable would produce a donor pool that looks real,
carries real-looking exclusion reasons, and is fiction. ADR-009 already settles
the principle for observations — *failure raises, it never falls back* — and it
applies with more force here, because the unit set is upstream of every number
the pipeline produces. :class:`EarthEngineUnitConstruction` therefore raises
:class:`DataUnavailableError` on every call until it is implemented.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from groundtruth.contracts.errors import DataUnavailableError
from groundtruth.contracts.identifiers import DatasetRef
from groundtruth.logging import get_logger
from groundtruth.platform.units.boundary import RegistryBoundary
from groundtruth.platform.units.rules import DistrictFacts
from groundtruth.platform.units.spec import (
    ADMINISTRATIVE_ASSET,
    BASELINE_FOREST_ASSET,
    BASELINE_FOREST_BAND,
    ECOREGION_ASSET,
    PERMANENT_WATER_ASSET,
    PERMANENT_WATER_BAND,
    PROTECTED_AREA_ASSET,
    Adr011Thresholds,
    Rung,
    RunParameters,
)

logger = get_logger("units.provider")


@runtime_checkable
class UnitConstructionService(Protocol):
    """Measures the facts ADR-011's rules need. Implemented by the platform.

    An implementation must apply the mask identically to the project and to
    every candidate, with two carve-outs ADR-011 states explicitly: the leakage
    belt is not applied to the project, and the case under test is excluded from
    the registered-carbon-project layer it would otherwise be subtracted by.
    """

    def treated_eligible_area_km2(
        self,
        boundary: RegistryBoundary,
        *,
        parameters: RunParameters,
        thresholds: Adr011Thresholds,
    ) -> float:
        """Eligible area of the treated unit after the full mask and inward buffer."""
        ...

    def districts_for_rung(
        self,
        rung: Rung,
        boundary: RegistryBoundary,
        *,
        parameters: RunParameters,
        thresholds: Adr011Thresholds,
    ) -> list[DistrictFacts]:
        """Masked facts for every administrative district in a rung's search region."""
        ...

    def dataset_refs(self, parameters: RunParameters) -> tuple[DatasetRef, ...]:
        """The pinned inputs used, for the unit-set manifest."""
        ...


def declared_dataset_refs(parameters: RunParameters) -> tuple[DatasetRef, ...]:
    """The inputs ADR-011 names, pinned as far as the parameters allow.

    Versions that a caller has not pinned are recorded as ``"unpinned"`` rather
    than invented. An unpinned input is a visible hole in the manifest, which is
    the intended behaviour: ADR-009 would rather show the weakness than imply it
    away.
    """
    return (
        DatasetRef(
            dataset_id="gaul-2015-level2",
            version="2015",
            provider="google-earth-engine",
            asset=ADMINISTRATIVE_ASSET,
        ),
        DatasetRef(
            dataset_id="resolve-ecoregions-2017",
            version="2017",
            provider="google-earth-engine",
            asset=ECOREGION_ASSET,
        ),
        DatasetRef(
            dataset_id="hansen-gfc",
            version="2023-v1.11",
            provider="google-earth-engine",
            asset=f"{BASELINE_FOREST_ASSET}#{BASELINE_FOREST_BAND}",
        ),
        DatasetRef(
            dataset_id="jrc-global-surface-water",
            version="1.4",
            provider="google-earth-engine",
            asset=f"{PERMANENT_WATER_ASSET}#{PERMANENT_WATER_BAND}",
        ),
        DatasetRef(
            dataset_id="wdpa",
            version=parameters.wdpa_release or "unpinned",
            provider="google-earth-engine",
            asset=PROTECTED_AREA_ASSET,
        ),
        DatasetRef(
            dataset_id="registered-carbon-projects",
            version=parameters.carbon_registry_snapshot_date or "unpinned",
            provider="berkeley-carbon-trading-project",
        ),
    )


class EarthEngineUnitConstruction:
    """ADR-011 masking backed by Earth Engine. **Not implemented.**

    The reduction chain an implementation owes, in ADR-011's fixed order:

    1. ``FAO/GAUL/2015/level2`` filtered to the rung's countries.
    2. Intersect with ``RESOLVE/ECOREGIONS/2017`` filtered to the rung's literal
       ``ECO_NAME`` values, and compute each district's baseline-forest share in
       those ecoregions *before* any subtraction — that share is the ≥50% rule.
    3. Intersect with Hansen ``treecover2000 >= 30``.
    4. Subtract JRC GSW ``occurrence >= 90`` over the full record, uniformly,
       with no per-unit exception.
    5. Subtract WDPA polygons with ``STATUS_YR <= 2000`` including ``0``, and
       ``STATUS`` in the designated/inscribed/established set.
    6. Subtract registered carbon-project geometry; flag districts containing a
       registry point whose geometry is unavailable.
    7. Erode by 300 m, applied last, to the masked geometry.
    8. Measure eligible area in the pinned equal-area projection.

    The project is built by steps 2-7 from its registry boundary, minus the
    leakage-belt rule, minus the ≥50%/band/floor admission rules, and with the
    case under test excluded from step 6 — otherwise the project is subtracted
    from itself and the treated unit is empty.
    """

    name = "earth-engine-adr011"

    def __init__(self, service_account_json: str | None = None) -> None:
        self.service_account_json = service_account_json

    @property
    def is_configured(self) -> bool:
        """True if Earth Engine credentials are present."""
        return bool(self.service_account_json)

    def _unavailable(self, what: str) -> DataUnavailableError:
        return DataUnavailableError(
            f"{what} requires the ADR-011 masking chain over pinned Earth Engine assets, which "
            "is not implemented (issues #23 for the datasets, #1/#22 for the client). "
            "Candidate generation refuses rather than returning units that were not measured."
        )

    def treated_eligible_area_km2(
        self,
        boundary: RegistryBoundary,
        *,
        parameters: RunParameters,
        thresholds: Adr011Thresholds,
    ) -> float:
        """Raises. See the class docstring for the chain this owes."""
        raise self._unavailable(f"the treated eligible area for {boundary.case_id!r}")

    def districts_for_rung(
        self,
        rung: Rung,
        boundary: RegistryBoundary,
        *,
        parameters: RunParameters,
        thresholds: Adr011Thresholds,
    ) -> list[DistrictFacts]:
        """Raises. See the class docstring for the chain this owes."""
        raise self._unavailable(f"district facts for ladder rung {rung.number}")

    def dataset_refs(self, parameters: RunParameters) -> tuple[DatasetRef, ...]:
        """The inputs this provider would use, which is knowable without running it."""
        return declared_dataset_refs(parameters)
