"""The Earth Engine covariate service: the platform's ``CovariateAccess``.

**Owner: Bhumi** (#23). Viraj decides which covariates matter and how they are
defined (coordination point C4, ``engine/features``); this service fetches them
and returns **raw values** in the units their names state. It applies no
transform: ``log1p`` and friends stay in the engine.

The definitions below were agreed with Viraj (C4), 2026-11-05:

* every covariate is measured over the **masked** unit (ADR-011), at the dataset's
  native scale;
* ``rainfall_mm``: CHIRPS daily, mean annual total over calendar 2001-2010;
* ``elevation_m``: mean of SRTM;
* ``slope_deg``: slope per pixel from SRTM first, then the mean;
* ``road_distance_km``: mean distance to the nearest road;
* ``population_density``: WorldPop 2000, summed population / the unit's eligible
  area, in people per km².

A missing value raises rather than being left out. ``match_donors`` drops a
candidate with a missing covariate and records no reason, so a partial answer here
would quietly remove a donor. Nothing on this path reads the synthetic provider.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from groundtruth.contracts.errors import ConfigurationError, DataUnavailableError
from groundtruth.contracts.identifiers import DatasetRef
from groundtruth.contracts.request import UnitRef
from groundtruth.logging import get_logger
from groundtruth.platform.datasets.cache import ReductionCache, cache_key
from groundtruth.platform.datasets.catalog import CATALOG_URL, PROVIDER
from groundtruth.platform.datasets.ee_mask import split_unit_geometry
from groundtruth.platform.datasets.observation import geometry_fingerprint
from groundtruth.platform.datasets.session import EarthEngineSession

logger = get_logger("datasets.covariates")

RAINFALL_YEARS = (2001, 2010)
"""V3: the mean annual total over the pre-period's calendar years."""

POPULATION_YEAR = 2000
"""V2: matches Hansen ``treecover2000``, the year the mask is dated to."""

CHIRPS_ASSET = "UCSB-CHG/CHIRPS/DAILY"
SRTM_ASSET = "USGS/SRTMGL1_003"
WORLDPOP_ASSET = "WorldPop/GP/100m/pop"
"""Deprecated in the Earth Engine catalog. Its replacement starts in 2015, after
treatment, so this is the asset with a 2000 image. The listing network test checks
that the image still exists."""

ROAD_SOURCE_GROADS = "groads-v1"
ROAD_SOURCE_OSM = "osm-current"
ROAD_SOURCES = (ROAD_SOURCE_GROADS, ROAD_SOURCE_OSM)

MASK_RULE_FRACTION = "fraction-weighted"
MASK_RULE_CENTRE = "pixel-centre"
MASK_RULES = (MASK_RULE_FRACTION, MASK_RULE_CENTRE)
"""How a 30 m mask is applied to a coarser covariate pixel. See :class:`CovariateQuery`."""

COVARIATE_KEYS = (
    "rainfall_mm",
    "elevation_m",
    "slope_deg",
    "road_distance_km",
    "population_density",
)

NON_NEGATIVE = frozenset({"rainfall_mm", "slope_deg", "road_distance_km", "population_density"})
"""A negative value here is a data fault, and ``log1p`` would refuse it later anyway."""


@dataclass(frozen=True)
class RoadSource:
    """The road layer, named explicitly, and how its distance raster is built.

    Roads are not an Earth Engine asset either way (V1), so the layer is an uploaded
    asset of our own, pinned by asset id, source file hash and upload date.
    """

    source: str
    asset: str
    source_sha256: str
    upload_date: str
    distance_scale_m: float
    search_radius_km: float

    def __post_init__(self) -> None:
        if self.source not in ROAD_SOURCES:
            raise ConfigurationError(
                f"unknown road source {self.source!r}; expected one of {ROAD_SOURCES}"
            )


def covariate_datasets(road: RoadSource) -> dict[str, DatasetRef]:
    """The pinned dataset behind each covariate.

    ``version`` carries the release **and** the reference year or epoch of the
    variable (``;ref=``), because only the second decides whether an input is
    pre-treatment, and the version is what reaches ``spec_hash``. A proper
    ``DatasetRef`` field would be a contract change (C1).
    """
    chirps = DatasetRef(
        dataset_id="chirps-daily",
        version=f"2.0-final;ref={RAINFALL_YEARS[0]}-{RAINFALL_YEARS[1]}",
        provider=PROVIDER,
        asset=CHIRPS_ASSET,
        source_uri=CATALOG_URL + CHIRPS_ASSET.replace("/", "_"),
    )
    srtm = DatasetRef(
        dataset_id="srtm-gl1",
        version="v3;ref=2000-02",
        provider=PROVIDER,
        asset=SRTM_ASSET,
        source_uri=CATALOG_URL + SRTM_ASSET.replace("/", "_"),
    )
    worldpop = DatasetRef(
        dataset_id="worldpop-gp-100m",
        version=f"gp-100m;ref={POPULATION_YEAR}",
        provider=PROVIDER,
        asset=WORLDPOP_ASSET,
        source_uri=CATALOG_URL + WORLDPOP_ASSET.replace("/", "_"),
    )
    if road.source == ROAD_SOURCE_GROADS:
        roads = DatasetRef(
            dataset_id="groads-v1",
            version=f"v1+sha256:{road.source_sha256};uploaded={road.upload_date};ref=1980-2010",
            provider=PROVIDER,
            asset=road.asset,
            source_uri="https://doi.org/10.7927/H4VD6WCT",
        )
    else:
        roads = DatasetRef(
            dataset_id="osm-roads",
            version=f"extract+sha256:{road.source_sha256};uploaded={road.upload_date};ref=present",
            provider=PROVIDER,
            asset=road.asset,
            source_uri="https://www.openstreetmap.org",
        )
    return {
        "rainfall_mm": chirps,
        "elevation_m": srtm,
        "slope_deg": srtm,
        "road_distance_km": roads,
        "population_density": worldpop,
    }


def covariate_definition(key: str, road: RoadSource) -> dict[str, Any]:
    """What one covariate is, as plain data: sent to the backend and part of the cache key."""
    if key == "rainfall_mm":
        return {
            "key": key,
            "kind": "mean-annual-total",
            "asset": CHIRPS_ASSET,
            "band": "precipitation",
            "first_year": RAINFALL_YEARS[0],
            "last_year": RAINFALL_YEARS[1],
            "statistic": "mean",
        }
    if key == "elevation_m":
        return {
            "key": key,
            "kind": "elevation",
            "asset": SRTM_ASSET,
            "band": "elevation",
            "statistic": "mean",
        }
    if key == "slope_deg":
        return {
            "key": key,
            "kind": "slope",
            "asset": SRTM_ASSET,
            "band": "elevation",
            "statistic": "mean",
        }
    if key == "road_distance_km":
        return {
            "key": key,
            "kind": "distance-to-road",
            "asset": road.asset,
            "scale_m": road.distance_scale_m,
            "search_radius_km": road.search_radius_km,
            "statistic": "mean",
        }
    if key == "population_density":
        return {
            "key": key,
            "kind": "population-count",
            "asset": WORLDPOP_ASSET,
            "band": "population",
            "year": POPULATION_YEAR,
            "statistic": "sum",
        }
    raise DataUnavailableError(
        f"no covariate service for {key!r}; served covariates are {list(COVARIATE_KEYS)}"
    )


@dataclass(frozen=True)
class CovariateQuery:
    """One covariate over one masked unit.

    ``mask_rule`` says how the 30 m mask meets a coarser covariate pixel (a CHIRPS
    pixel is ~5.5 km). ``fraction-weighted`` weights each coarse pixel by the share of
    its area that is eligible; ``pixel-centre`` keeps it only if the mask is set at
    its centre. V4 fixes the native scale but not this, so it is a required setting.
    """

    outline: Mapping[str, Any]
    recipe: Mapping[str, Any]
    covariate: Mapping[str, Any]
    mask_rule: str


class CovariateBackend(Protocol):
    """What the covariate service needs from Earth Engine. Faked in tests."""

    def reduce_covariate(self, query: CovariateQuery) -> dict[str, Any]:
        """``{"value": float | None, "unreachable_pixels": number}``."""
        ...


class EarthEngineCovariateAccess:
    """``CovariateAccess`` over Google Earth Engine, for ADR-011 masked units.

    Args:
        session: The shared Earth Engine session.
        backend: The backend ``session`` signed in.
        road: The explicitly named road source.
        mask_rule: One of :data:`MASK_RULES`. Required; there is no default.
        cache: Where reduced covariates are cached; ``None`` disables caching.
    """

    def __init__(
        self,
        *,
        session: EarthEngineSession,
        backend: CovariateBackend,
        road: RoadSource,
        mask_rule: str,
        cache: ReductionCache | None = None,
    ) -> None:
        if mask_rule not in MASK_RULES:
            raise ConfigurationError(
                f"unknown native-scale mask rule {mask_rule!r}; expected one of {MASK_RULES}"
            )
        self._session = session
        self._backend = backend
        self.road = road
        self.mask_rule = mask_rule
        self._cache = cache
        self._datasets = covariate_datasets(road)

    def dataset(self, key: str) -> DatasetRef:
        """The pinned dataset backing one covariate."""
        if key not in self._datasets:
            raise DataUnavailableError(f"no pinned dataset for covariate {key!r}")
        return self._datasets[key]

    def covariates(self, unit: UnitRef, keys: tuple[str, ...]) -> dict[str, float]:
        """The requested covariates for one masked unit, raw, in their stated units.

        Raises:
            DataUnavailableError: if the unit is not an ADR-011 masked unit, a key is
                not served, or any value cannot be measured.
        """
        if unit.geometry is None:
            raise DataUnavailableError(f"unit {unit.unit_id!r} has no geometry to measure")
        outline, recipe = split_unit_geometry(unit.geometry)
        if recipe is None:
            raise DataUnavailableError(
                f"unit {unit.unit_id!r} has no ADR-011 mask recipe; covariates are measured "
                "over the masked unit, never its bare outline (V4)"
            )
        geometry_hash = geometry_fingerprint(unit.geometry)
        return {
            key: self._value(unit, outline, recipe, key, geometry_hash)
            for key in dict.fromkeys(keys)
        }

    def _value(
        self,
        unit: UnitRef,
        outline: Mapping[str, Any],
        recipe: Mapping[str, Any],
        key: str,
        geometry_hash: str,
    ) -> float:
        definition = covariate_definition(key, self.road)
        raw = self._raw(unit, outline, recipe, key, definition, geometry_hash)
        value = raw
        if definition["statistic"] == "sum":
            if not unit.area_ha:
                raise DataUnavailableError(
                    f"unit {unit.unit_id!r} has no eligible area, so {key} cannot be computed"
                )
            value = raw / (unit.area_ha / 100.0)
        if key in NON_NEGATIVE and value < 0:
            raise DataUnavailableError(
                f"{key} for unit {unit.unit_id!r} came back negative ({value}); refusing it"
            )
        return value

    def _raw(
        self,
        unit: UnitRef,
        outline: Mapping[str, Any],
        recipe: Mapping[str, Any],
        key: str,
        definition: Mapping[str, Any],
        geometry_hash: str,
    ) -> float:
        ref = self._datasets[key]
        material = cache_key(
            kind="adr011-covariate",
            dataset=ref.model_dump(mode="json", exclude={"retrieved_at"}),
            covariate=dict(definition),
            geometry_blake2b=geometry_hash,
            mask_rule=self.mask_rule,
        )
        if self._cache is not None:
            stored = self._cache.get(material)
            if stored is not None and isinstance(stored.get("value"), int | float):
                return float(stored["value"])

        query = CovariateQuery(
            outline=outline, recipe=recipe, covariate=definition, mask_rule=self.mask_rule
        )
        reduced = self._session.call(
            f"{key} for unit {unit.unit_id}", lambda: self._backend.reduce_covariate(query)
        )
        value = reduced.get("value")
        if value is None:
            raise DataUnavailableError(
                f"{key} has no value over unit {unit.unit_id!r}: no eligible pixel has data. "
                "It is reported as missing, never filled."
            )
        unreachable = float(reduced.get("unreachable_pixels") or 0)
        if unreachable > 0:
            raise DataUnavailableError(
                f"{key} for unit {unit.unit_id!r}: {unreachable:.0f} eligible pixels are further "
                f"than the {self.road.search_radius_km:g} km search radius, so a mean over the "
                "rest would understate the distance. Refusing rather than biasing it."
            )
        if self._cache is not None:
            self._cache.put(
                material, {"value": float(value), "retrieved_at": datetime.now(UTC).isoformat()}
            )
        return float(value)


__all__ = [
    "COVARIATE_KEYS",
    "MASK_RULES",
    "POPULATION_YEAR",
    "RAINFALL_YEARS",
    "ROAD_SOURCES",
    "ROAD_SOURCE_GROADS",
    "ROAD_SOURCE_OSM",
    "WORLDPOP_ASSET",
    "CovariateBackend",
    "CovariateQuery",
    "EarthEngineCovariateAccess",
    "RoadSource",
    "covariate_datasets",
    "covariate_definition",
]
