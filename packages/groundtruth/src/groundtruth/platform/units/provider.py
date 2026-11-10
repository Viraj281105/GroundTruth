"""The masking port, and its Earth Engine implementation.

ADR-011's eligibility mask is five raster and vector operations over pinned
assets:

``district ∩ target_ecoregions ∩ baseline_forest MINUS permanent_water MINUS
protected_areas MINUS registered_carbon_projects ⊖ inward_buffer(300 m)``

:class:`EarthEngineUnitConstruction` measures the facts the rules layer needs, over
the raster form of that mask (``docs/decisions/ADR-011-amendment-1-raster-units.md``,
V6, agreed with Viraj (C4), 2026-11-05). It measures only: every decision about a
district stays in :mod:`~groundtruth.platform.units.rules`.

**Why there is no local fallback.** A provider that returned plausible districts
when the real ones were unavailable would produce a donor pool that looks real,
carries real-looking exclusion reasons, and is fiction. ADR-009 already settles
the principle for observations — *failure raises, it never falls back* — and it
applies with more force here, because the unit set is upstream of every number
the pipeline produces. Without an Earth Engine session every measurement raises
:class:`DataUnavailableError`.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

from groundtruth.contracts.errors import DataUnavailableError
from groundtruth.contracts.identifiers import DatasetRef, spec_hash
from groundtruth.contracts.request import UnitRef
from groundtruth.logging import get_logger
from groundtruth.platform.datasets.cache import ReductionCache, cache_key
from groundtruth.platform.datasets.covariates import COVARIATE_KEYS, POPULATION_YEAR, WORLDPOP_ASSET
from groundtruth.platform.datasets.ee_mask import (
    MASK_KIND,
    MASK_VERSION,
    unit_geometry,
)
from groundtruth.platform.datasets.ee_units import MaskQuery
from groundtruth.platform.datasets.session import EarthEngineSession
from groundtruth.platform.units.boundary import RegistryBoundary
from groundtruth.platform.units.carbon_projects import CarbonProjectSnapshot
from groundtruth.platform.units.rules import DistrictFacts, evaluate_district
from groundtruth.platform.units.spec import (
    ADMINISTRATIVE_ASSET,
    BASELINE_FOREST_ASSET,
    BASELINE_FOREST_BAND,
    ECOREGION_ASSET,
    GAUL_ADM0_NAMES,
    PERMANENT_WATER_ASSET,
    PERMANENT_WATER_BAND,
    PROTECTED_AREA_ASSET_FOLDER,
    STUDY_BOUNDS,
    UNIT_ID_PREFIX,
    Adr011Thresholds,
    Rung,
    RunParameters,
    protected_area_asset,
)

logger = get_logger("units.provider")

M2_PER_KM2 = 1_000_000.0
M2_PER_HA = 10_000.0


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

    ``version`` carries the release and, after ``;ref=``, the reference year or epoch
    of the variable. They are different facts and only the second decides whether an
    input is pre-treatment. A proper ``DatasetRef`` field would be a contract change
    (C1); until then this is what reaches ``spec_hash``.

    Versions that a caller has not pinned are recorded as ``"unpinned"`` rather
    than invented. An unpinned input is a visible hole in the manifest, which is
    the intended behaviour: ADR-009 would rather show the weakness than imply it
    away.
    """
    return (
        DatasetRef(
            dataset_id="gaul-2015-level2",
            version="2015;ref=2014-2015",
            provider="google-earth-engine",
            asset=ADMINISTRATIVE_ASSET,
        ),
        DatasetRef(
            dataset_id="resolve-ecoregions-2017",
            version="2017;ref=time-invariant",
            provider="google-earth-engine",
            asset=ECOREGION_ASSET,
        ),
        DatasetRef(
            dataset_id="hansen-gfc",
            version="2023-v1.11;ref=2000",
            provider="google-earth-engine",
            asset=f"{BASELINE_FOREST_ASSET}#{BASELINE_FOREST_BAND}",
        ),
        DatasetRef(
            dataset_id="jrc-global-surface-water",
            version="1.4;ref=1984-2021",
            provider="google-earth-engine",
            asset=f"{PERMANENT_WATER_ASSET}#{PERMANENT_WATER_BAND}",
        ),
        DatasetRef(
            dataset_id="wdpa",
            version=f"{parameters.wdpa_release or 'unpinned'};ref=status-year-2000-or-earlier",
            provider="google-earth-engine",
            asset=protected_area_asset(parameters.wdpa_release or "unpinned"),
        ),
        DatasetRef(
            dataset_id="registered-carbon-projects",
            version=(
                f"{parameters.carbon_registry_snapshot_date or 'unpinned'};ref=up-to-snapshot"
            ),
            provider="berkeley-carbon-trading-project",
        ),
    )


def build_mask_recipe(
    *,
    parameters: RunParameters,
    thresholds: Adr011Thresholds,
    ecoregion_names: Sequence[str],
    carbon_projects: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    """Everything needed to rebuild a unit's mask, as plain data.

    It is hashed into the unit's geometry and travels with the unit, so nothing about
    the mask depends on reading this code's defaults later.
    """
    radius_pixels = thresholds.inward_buffer_m / parameters.raster_scale_m
    if radius_pixels != int(radius_pixels):
        raise DataUnavailableError(
            f"the {thresholds.inward_buffer_m:g} m inward buffer is not a whole number of "
            f"{parameters.raster_scale_m:g} m pixels"
        )
    return {
        "kind": MASK_KIND,
        "version": MASK_VERSION,
        "crs": parameters.projection,
        "scale_m": parameters.raster_scale_m,
        "resampling": parameters.raster_reducer,
        "target_ecoregions": {
            "asset": ECOREGION_ASSET,
            "property": "ECO_NAME",
            "names": list(ecoregion_names),
        },
        "baseline_forest": {
            "asset": BASELINE_FOREST_ASSET,
            "band": BASELINE_FOREST_BAND,
            "min_percent": thresholds.treecover_2000_min_percent,
        },
        "permanent_water": {
            "asset": PERMANENT_WATER_ASSET,
            "band": PERMANENT_WATER_BAND,
            "min_percent": thresholds.water_occurrence_min_percent,
        },
        "protected_areas": {
            "asset": protected_area_asset(parameters.wdpa_release),
            "status_year_max": thresholds.wdpa_status_year_max,
            "status_values": list(thresholds.wdpa_status_values),
        },
        "carbon_projects": [dict(project) for project in carbon_projects],
        "erosion": {
            "radius_m": thresholds.inward_buffer_m,
            "radius_pixels": int(radius_pixels),
            "kernel": "circle",
        },
    }


class EarthEngineUnitConstruction:
    """ADR-011 masking backed by Earth Engine.

    The chain, in ADR-011's fixed order:

    1. ``FAO/GAUL/2015/level2`` filtered to the rung's countries.
    2. Intersect with ``RESOLVE/ECOREGIONS/2017`` filtered to the rung's literal
       ``ECO_NAME`` values, and compute each district's baseline-forest share in
       those ecoregions *before* any subtraction — that share is the ≥50% rule.
    3. Intersect with Hansen ``treecover2000 >= 30``.
    4. Subtract JRC GSW ``occurrence >= 90`` over the full record, uniformly,
       with no per-unit exception.
    5. Subtract WDPA polygons with ``STATUS_YR <= 2000`` including ``0``, and
       ``STATUS`` in the designated/inscribed/established set.
    6. Subtract registered carbon-project geometry; flag districts the committed
       snapshot lists as holding a project with no geometry.
    7. Erode by 300 m, applied last, to the masked raster.
    8. Measure eligible area in the pinned equal-area projection.

    The project is built by steps 2-7 from its registry boundary, minus the
    leakage-belt rule, minus the ≥50%/band/floor admission rules, and with the
    case under test excluded from step 6 — otherwise the project is subtracted
    from itself and the treated unit is empty.

    Args:
        session: The shared Earth Engine session. Without one, every measurement
            raises, which is what makes ``EarthEngineUnitConstruction()`` safe to use
            for declaring dataset refs.
        backend: The backend ``session`` signed in.
        cache: Where measurements are cached, per district, so a timeout loses only
            the district it hit. ``None`` disables caching.
        carbon_projects: The committed registered-projects snapshot.
        case_registry_id: The case under test, excluded from its own subtraction.
        treated_ecoregion_key: Which rung's ecoregions define the treated unit's mask.
            ADR-011 does not say; it is a required run setting.
    """

    name = "earth-engine-adr011"

    def __init__(
        self,
        *,
        session: EarthEngineSession | None = None,
        backend: Any = None,
        cache: ReductionCache | None = None,
        carbon_projects: CarbonProjectSnapshot | None = None,
        case_registry_id: str | None = None,
        treated_ecoregion_key: str | None = None,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._session = session
        self._backend = backend
        self._cache = cache
        self._carbon = carbon_projects
        self._case_registry_id = case_registry_id
        self._treated_key = treated_ecoregion_key
        self._clock = clock
        self._wdpa_checked = False

    def _ready(self, what: str) -> tuple[EarthEngineSession, Any, CarbonProjectSnapshot]:
        if self._session is None or self._backend is None or self._carbon is None:
            raise DataUnavailableError(
                f"{what} requires the ADR-011 masking chain over pinned Earth Engine assets, and "
                "this provider was built without an Earth Engine session or a carbon-project "
                "snapshot (#23). Candidate generation refuses rather than returning units that "
                "were not measured."
            )
        return self._session, self._backend, self._carbon

    # --- listings, for fixing the open parameters ----------------------------------

    def study_area_listing(self) -> dict[str, list[str]]:
        """Literal names to fix the open parameters from. Names only, never a count.

        V5 requires the ``ECO_NAME`` strings to be copied from this listing rather than
        from ADR prose, and V2 requires the WorldPop 2000 image to be confirmed to exist.
        """
        if self._session is None or self._backend is None:
            raise DataUnavailableError("the listing needs an Earth Engine session")
        session, backend = self._session, self._backend
        bounds = STUDY_BOUNDS
        releases = session.call(
            "WDPA snapshot listing",
            lambda: backend.list_wdpa_releases(
                f"projects/earthengine-public/assets/{PROTECTED_AREA_ASSET_FOLDER}"
            ),
        )
        return {
            "eco_names": session.call(
                "ECO_NAME listing", lambda: backend.list_ecoregion_names(ECOREGION_ASSET, bounds)
            ),
            "wdpa_releases": releases,
            "gaul_countries": session.call(
                "GAUL country listing",
                lambda: backend.list_admin_countries(ADMINISTRATIVE_ASSET, bounds),
            ),
            "worldpop_2000_countries": session.call(
                "WorldPop 2000 listing",
                lambda: backend.list_worldpop_countries(WORLDPOP_ASSET, POPULATION_YEAR, bounds),
            ),
        }

    # --- the port --------------------------------------------------------------------

    def treated_eligible_area_km2(
        self,
        boundary: RegistryBoundary,
        *,
        parameters: RunParameters,
        thresholds: Adr011Thresholds,
    ) -> float:
        """Eligible area of the treated unit after the full mask and inward buffer."""
        unit = self.treated_unit(boundary, parameters=parameters, thresholds=thresholds)
        return unit.attributes["eligible_area_km2"]

    def treated_unit(
        self,
        boundary: RegistryBoundary,
        *,
        parameters: RunParameters,
        thresholds: Adr011Thresholds,
    ) -> UnitRef:
        """The treated unit under the same mask as every candidate.

        Raises:
            DataUnavailableError: if the mask cannot be measured, or leaves protected
                land inside the unit.
        """
        _, _, carbon = self._ready(f"the treated eligible area for {boundary.case_id!r}")
        if self._treated_key is None:
            raise DataUnavailableError(
                "no treated_ecoregion_rung was supplied; which rung's ecoregions define the "
                "treated unit's mask is a required run setting"
            )
        names = parameters.ecoregion_names.get(self._treated_key)
        if not names:
            raise DataUnavailableError(
                f"no ECO_NAME values pinned for the treated unit's rung {self._treated_key!r}"
            )
        recipe = build_mask_recipe(
            parameters=parameters,
            thresholds=thresholds,
            ecoregion_names=names,
            # ADR-011: every registered project except the case under test, which would
            # otherwise subtract the project from itself.
            carbon_projects=carbon.recipe_entries(exclude=self._case_registry_id),
        )
        self._check_wdpa(recipe)
        query = MaskQuery(outline=boundary.geometry, recipe=recipe)
        measured = self._measure_mask(boundary.case_id, query)
        eligible_pixels = _pixels(measured, "eligible")
        area_km2 = eligible_pixels * parameters.raster_scale_m**2 / M2_PER_KM2
        return UnitRef(
            unit_id=boundary.case_id,
            geometry=unit_geometry(boundary.geometry, recipe),
            area_ha=(area_km2 * 100.0) if area_km2 > 0 else None,
            attributes={
                "eligible_area_km2": area_km2,
                "boundary_area_km2": boundary.boundary_area_km2,
            },
        )

    def districts_for_rung(
        self,
        rung: Rung,
        boundary: RegistryBoundary,
        *,
        parameters: RunParameters,
        thresholds: Adr011Thresholds,
    ) -> list[DistrictFacts]:
        """Masked facts for every GAUL district in a rung's countries.

        Measuring runs one district at a time and each step is cached, so a timeout
        loses only that step, and the failure raises with nothing partial returned.
        """
        session, backend, carbon = self._ready(f"district facts for ladder rung {rung.number}")
        names = parameters.ecoregions_for(rung)
        recipe = build_mask_recipe(
            parameters=parameters,
            thresholds=thresholds,
            ecoregion_names=names,
            carbon_projects=carbon.recipe_entries(),
        )
        self._check_wdpa(recipe)
        treated_area = self.treated_eligible_area_km2(
            boundary, parameters=parameters, thresholds=thresholds
        )
        adm0_names = _adm0_names(rung)
        districts = session.call(
            f"district listing for rung {rung.number}",
            lambda: backend.list_districts(ADMINISTRATIVE_ASSET, adm0_names),
        )
        missing = sorted(set(adm0_names) - {d["adm0_name"] for d in districts})
        if missing:
            raise DataUnavailableError(
                f"GAUL returned no districts for {missing}; the search region would silently "
                "shrink. Check the names against the listing network test."
            )
        belt = self._belt(boundary, parameters=parameters, thresholds=thresholds)
        in_belt = {
            str(code)
            for code in session.call(
                f"leakage-belt districts for rung {rung.number}",
                lambda: backend.districts_in_belt(ADMINISTRATIVE_ASSET, adm0_names, belt),
            )
        }
        iso3_by_name = {GAUL_ADM0_NAMES[iso3]: iso3 for iso3 in rung.countries}
        excluded_whole = set(parameters.excluded_carbon_project_districts)

        facts: list[DistrictFacts] = []
        for district in sorted(districts, key=lambda d: str(d["adm2_code"])):
            code = str(district["adm2_code"])
            facts.append(
                self._district(
                    code=code,
                    country=iso3_by_name[district["adm0_name"]],
                    recipe=recipe,
                    parameters=parameters,
                    thresholds=thresholds,
                    treated_area_km2=treated_area,
                    intersects_belt=code in in_belt,
                    excluded_whole=f"{UNIT_ID_PREFIX}:{code}" in excluded_whole,
                )
            )
        return facts

    def dataset_refs(self, parameters: RunParameters) -> tuple[DatasetRef, ...]:
        """The inputs this provider uses, which is knowable without running it."""
        return declared_dataset_refs(parameters)

    # --- the belt ---------------------------------------------------------------------

    def _belt(
        self,
        boundary: RegistryBoundary,
        *,
        parameters: RunParameters,
        thresholds: Adr011Thresholds,
    ) -> dict[str, Any]:
        session, backend, _ = self._ready("the leakage belt")
        radius_m = thresholds.leakage_belt_km * 1000.0
        belt: dict[str, Any] = self._cached(
            cache_key(
                kind="adr011-belt",
                boundary_sha256=boundary.content_sha256,
                radius_m=radius_m,
                max_error_m=parameters.simplification_max_error_m,
                crs=parameters.projection,
            ),
            lambda: session.call(
                "leakage-belt buffer",
                lambda: backend.leakage_belt(
                    boundary.geometry,
                    radius_m,
                    parameters.simplification_max_error_m,
                    parameters.projection,
                ),
            ),
        )
        return belt

    def leakage_belt_hash(
        self,
        boundary: RegistryBoundary,
        *,
        parameters: RunParameters,
        thresholds: Adr011Thresholds,
    ) -> str:
        """Hash of the 10 km belt around the unmasked boundary, for the manifest."""
        return spec_hash(self._belt(boundary, parameters=parameters, thresholds=thresholds))

    # --- one district -----------------------------------------------------------------

    def _district(
        self,
        *,
        code: str,
        country: str,
        recipe: Mapping[str, Any],
        parameters: RunParameters,
        thresholds: Adr011Thresholds,
        treated_area_km2: float,
        intersects_belt: bool,
        excluded_whole: bool,
    ) -> DistrictFacts:
        unit_id = f"{UNIT_ID_PREFIX}:{code}"
        session, backend, _ = self._ready(f"facts for {unit_id}")
        outline: dict[str, Any] = self._cached(
            cache_key(kind="adr011-outline", asset=ADMINISTRATIVE_ASSET, adm2_code=code),
            lambda: session.call(
                f"outline of {unit_id}",
                lambda: backend.district_outline(ADMINISTRATIVE_ASSET, code),
            ),
        )
        query = MaskQuery(outline=outline, recipe=recipe)
        forest = self._cached(
            self._step_key("forest", query),
            lambda: session.call(f"forest of {unit_id}", lambda: backend.measure_forest(query)),
        )
        forest_pixels = _pixels(forest, "forest")
        in_ecoregions = _pixels(forest, "forest_in_ecoregions")
        share = in_ecoregions / forest_pixels if forest_pixels else 0.0

        # No forest in a target ecoregion means an empty mask, exactly: the mask is a
        # subset of that layer. Skipping the erosion here changes no result.
        eligible_pixels = 0
        if in_ecoregions > 0:
            eligible_pixels = _pixels(self._measure_mask(unit_id, query), "eligible")

        area_km2 = eligible_pixels * parameters.raster_scale_m**2 / M2_PER_KM2
        geometry = unit_geometry(outline, recipe) if eligible_pixels else None
        facts = DistrictFacts(
            unit_id=unit_id,
            adm2_code=code,
            country=country,
            eligible_area_km2=area_km2,
            forest_share_in_target_ecoregions=share,
            intersects_leakage_belt=intersects_belt,
            contains_registered_project_without_geometry=excluded_whole,
            fragments=0,
            geometry_hash=spec_hash(
                {
                    "recipe": spec_hash(dict(recipe)),
                    "outline": spec_hash(outline),
                    "eligible_pixels": eligible_pixels,
                }
            ),
            eligible_pixels=eligible_pixels,
            geometry=geometry,
        )
        # The fragment count is the most expensive step, and it is recorded only for
        # units that stay in the pool. The rules decide that, not this method.
        if (
            evaluate_district(
                facts, project_eligible_area_km2=treated_area_km2, thresholds=thresholds
            )
            is not None
        ):
            return facts
        fragments = self._cached(
            self._step_key("fragments", query),
            lambda: {
                "fragments": session.call(
                    f"fragments of {unit_id}", lambda: backend.count_fragments(query)
                )
            },
        )
        return _with_fragments(facts, int(fragments["fragments"]))

    def _measure_mask(self, unit_id: str, query: MaskQuery) -> dict[str, Any]:
        session, backend, _ = self._ready(f"the mask of {unit_id}")
        measured: dict[str, Any] = self._cached(
            self._step_key("mask", query),
            lambda: session.call(f"mask of {unit_id}", lambda: backend.measure_mask(query)),
        )
        overlap = _pixels(measured, "protected_overlap")
        if overlap:
            raise DataUnavailableError(
                f"the mask of {unit_id} leaves {overlap} protected pixels inside the unit. ADR-011 "
                "subtracts them, so this is a fault in the chain, and it is never recorded as a "
                "usable unit."
            )
        return measured

    def _step_key(self, step: str, query: MaskQuery) -> dict[str, Any]:
        return cache_key(
            kind=f"adr011-{step}",
            recipe=dict(query.recipe),
            outline_blake2b=spec_hash(dict(query.outline)),
        )

    def _cached(
        self, key: Mapping[str, Any], fetch: Callable[[], dict[str, Any]]
    ) -> dict[str, Any]:
        if self._cache is not None:
            stored = self._cache.get(key)
            if stored is not None:
                return stored
        value = fetch()
        if self._cache is not None:
            self._cache.put(key, value)
        return value

    def _check_wdpa(self, recipe: Mapping[str, Any]) -> None:
        """Refuse if none of ADR-011's statuses appear in the snapshot.

        The filter matches exact strings. A case difference between the code and the
        asset would match nothing and silently subtract no protected land, which is the
        one failure this rule cannot afford, so it is checked before anything is measured.
        """
        if self._wdpa_checked:
            return
        session, backend, _ = self._ready("the WDPA status check")
        spec = recipe["protected_areas"]
        statuses = session.call(
            "WDPA status listing",
            lambda: backend.list_wdpa_statuses(spec["asset"], STUDY_BOUNDS),
        )
        if not set(spec["status_values"]) & set(statuses):
            raise DataUnavailableError(
                f"none of the statuses ADR-011 subtracts ({spec['status_values']}) appear in "
                f"{spec['asset']}, which lists {statuses}. Nothing would be subtracted, so "
                "refusing."
            )
        self._wdpa_checked = True

    # --- the timing trial (B6) --------------------------------------------------------

    def timing_trial(
        self,
        rung: Rung,
        boundary: RegistryBoundary,
        *,
        parameters: RunParameters,
        thresholds: Adr011Thresholds,
        covariates: Any = None,
    ) -> dict[str, float]:
        """How long each step takes on one district: seconds only, no counts.

        Runs before any batch work is considered (B6). It returns no area, no pixel
        count and no candidate count, and logs none, so running it cannot reveal
        anything a parameter could be tuned against. The cache is bypassed so the time
        is the real cost.
        """
        session, backend, carbon = self._ready("the timing trial")
        names = parameters.ecoregions_for(rung)
        recipe = build_mask_recipe(
            parameters=parameters,
            thresholds=thresholds,
            ecoregion_names=names,
            carbon_projects=carbon.recipe_entries(),
        )
        adm0_names = _adm0_names(rung)
        districts = session.call(
            "district listing", lambda: backend.list_districts(ADMINISTRATIVE_ASSET, adm0_names)
        )
        for district in sorted(districts, key=lambda d: str(d["adm2_code"])):
            seconds = self._trial_on_district(
                str(district["adm2_code"]), recipe, parameters, covariates
            )
            if seconds is not None:
                return seconds
        raise DataUnavailableError(
            f"rung {rung.number} has no district with an eligible pixel to time"
        )

    def _trial_on_district(
        self,
        code: str,
        recipe: Mapping[str, Any],
        parameters: RunParameters,
        covariates: Any,
    ) -> dict[str, float] | None:
        """Seconds per step on one district, or ``None`` if it has nothing to mask."""
        session, backend, _ = self._ready("the timing trial")
        seconds: dict[str, float] = {}
        outline = self._timed(
            seconds,
            "outline",
            lambda: session.call(
                "outline", lambda: backend.district_outline(ADMINISTRATIVE_ASSET, code)
            ),
        )
        query = MaskQuery(outline=outline, recipe=recipe)
        forest = self._timed(
            seconds, "forest", lambda: session.call("forest", lambda: backend.measure_forest(query))
        )
        if not _pixels(forest, "forest_in_ecoregions"):
            return None
        measured = self._timed(
            seconds, "mask", lambda: session.call("mask", lambda: backend.measure_mask(query))
        )
        eligible = _pixels(measured, "eligible")
        if not eligible:
            return None
        self._timed(
            seconds,
            "fragments",
            lambda: session.call("fragments", lambda: backend.count_fragments(query)),
        )
        if covariates is not None:
            unit = UnitRef(
                unit_id=f"{UNIT_ID_PREFIX}:{code}",
                geometry=unit_geometry(outline, recipe),
                area_ha=eligible * parameters.raster_scale_m**2 / M2_PER_HA,
            )
            for key in COVARIATE_KEYS:
                self._time_covariate(seconds, covariates, unit, key)
        return seconds

    def _time_covariate(
        self, seconds: dict[str, float], covariates: Any, unit: UnitRef, key: str
    ) -> None:
        self._timed(seconds, f"covariate:{key}", lambda: covariates.covariates(unit, (key,)))

    def _timed(self, seconds: dict[str, float], step: str, call: Callable[[], Any]) -> Any:
        started = self._clock()
        result = call()
        seconds[step] = self._clock() - started
        return result


def _adm0_names(rung: Rung) -> list[str]:
    return [GAUL_ADM0_NAMES[iso3] for iso3 in rung.countries]


def _pixels(measured: Mapping[str, Any], name: str) -> int:
    """A pixel count from a sum over a 0/1 image, which arrives as a float."""
    value = measured.get(name)
    if value is None:
        raise DataUnavailableError(f"Earth Engine returned no {name!r} measurement")
    return round(float(value))


def _with_fragments(facts: DistrictFacts, fragments: int) -> DistrictFacts:
    return DistrictFacts(
        unit_id=facts.unit_id,
        adm2_code=facts.adm2_code,
        country=facts.country,
        eligible_area_km2=facts.eligible_area_km2,
        forest_share_in_target_ecoregions=facts.forest_share_in_target_ecoregions,
        intersects_leakage_belt=facts.intersects_leakage_belt,
        contains_registered_project_without_geometry=(
            facts.contains_registered_project_without_geometry
        ),
        fragments=fragments,
        geometry_hash=facts.geometry_hash,
        eligible_pixels=facts.eligible_pixels,
        geometry=facts.geometry,
    )


__all__ = [
    "EarthEngineUnitConstruction",
    "UnitConstructionService",
    "build_mask_recipe",
    "declared_dataset_refs",
]
