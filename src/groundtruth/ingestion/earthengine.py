"""Google Earth Engine observation provider.

STATUS: interface implemented, Earth Engine calls NOT yet implemented.

Every method that would contact Earth Engine raises
:class:`~groundtruth.core.errors.DataUnavailableError` until the reducer chain
below is written and validated. This is intentional: a provider that silently
falls back to simulated numbers would be a correctness hazard in a verification
system. See issue "P0: implement Earth Engine NDVI/EVI reducer".

Implementation plan (docs/03-architecture.md, section 4):

1. ``ee.Initialize`` with a service account from ``GEE_SERVICE_ACCOUNT_JSON``.
2. Build a ``COPERNICUS/S2_SR_HARMONIZED`` collection filtered to the AOI and
   period, masked with the SCL band (and QA60 for legacy scenes).
3. Reduce to an annual median composite, then compute the requested index.
4. ``reduceRegion`` with ``ee.Reducer.mean().combine(ee.Reducer.count())`` to get
   both the value and the clear-sky observation count per period.
5. Return a ``TimeSeries`` with ``n_valid_observations`` populated so downstream
   stages can down-weight cloud-starved years.
"""

from __future__ import annotations

from typing import Any

from groundtruth.core.errors import ConfigurationError, DataUnavailableError
from groundtruth.core.provenance import Provenance
from groundtruth.core.types import Indicator, TimeSeries
from groundtruth.ingestion.base import AreaOfInterest, ObservationRequest
from groundtruth.logging import get_logger

logger = get_logger("ingestion.earthengine")

COLLECTIONS: dict[str, str] = {
    "sentinel2": "COPERNICUS/S2_SR_HARMONIZED",
    "landsat8": "LANDSAT/LC08/C02/T1_L2",
    "landsat9": "LANDSAT/LC09/C02/T1_L2",
    "hansen": "UMD/hansen/global_forest_change_2023_v1_11",
}

BAND_MAP: dict[str, dict[str, str]] = {
    "sentinel2": {"red": "B4", "nir": "B8", "blue": "B2", "swir": "B11", "scl": "SCL"},
    "landsat8": {"red": "SR_B4", "nir": "SR_B5", "blue": "SR_B2", "swir": "SR_B6"},
}


class EarthEngineProvider:
    """Observation provider backed by Google Earth Engine.

    Args:
        service_account_json: Path to, or contents of, a GEE service-account key.
        collection: Key into :data:`COLLECTIONS`.
        scale_m: Reduction scale in metres.
    """

    name = "google-earth-engine"

    def __init__(
        self,
        service_account_json: str | None,
        *,
        collection: str = "sentinel2",
        scale_m: int = 30,
    ) -> None:
        if collection not in COLLECTIONS:
            raise ConfigurationError(f"unknown collection {collection!r}")
        self.service_account_json = service_account_json
        self.collection = collection
        self.scale_m = scale_m
        self._client: Any | None = None

    @property
    def is_configured(self) -> bool:
        """True if credentials are present."""
        return bool(self.service_account_json)

    def provenance(self, request: ObservationRequest) -> Provenance:
        """Provenance describing the exact Earth Engine reduction used."""
        return Provenance.computed(
            source=COLLECTIONS[self.collection],
            method=f"annual-median-composite/{request.indicator.value}",
            stage="ingestion",
            parameters={
                "collection": COLLECTIONS[self.collection],
                "scale_m": self.scale_m,
                "max_cloud_fraction": request.max_cloud_fraction,
                "start_period": request.start_period,
                "end_period": request.end_period,
            },
            notes="Cloud/shadow masked via SCL; annual median composite.",
        )

    def initialize(self) -> None:
        """Authenticate against Earth Engine.

        Raises:
            ConfigurationError: if credentials are missing.
            DataUnavailableError: always, until the integration is implemented.
        """
        if not self.is_configured:
            raise ConfigurationError(
                "GEE_SERVICE_ACCOUNT_JSON is not set; cannot initialise Earth Engine."
            )
        raise DataUnavailableError(
            "EarthEngineProvider.initialize is not implemented yet. Run the pipeline with the "
            "synthetic provider, or implement the reducer chain documented in this module."
        )

    def fetch(self, request: ObservationRequest) -> TimeSeries:
        """Fetch a real indicator series. NOT IMPLEMENTED."""
        raise DataUnavailableError(
            f"EarthEngineProvider.fetch({request.indicator.value}) is not implemented yet. "
            "See docs/10-roadmap.md, milestone M1."
        )

    def index_expression(self, indicator: Indicator) -> str:
        """Return the band-math expression for an indicator.

        This part *is* implemented, because the formulae are fixed and testable
        independently of any network access.
        """
        bands = BAND_MAP.get(self.collection)
        if bands is None:
            raise ConfigurationError(f"no band map for collection {self.collection!r}")
        match indicator:
            case Indicator.NDVI:
                return f"({bands['nir']} - {bands['red']}) / ({bands['nir']} + {bands['red']})"
            case Indicator.EVI:
                return (
                    f"2.5 * (({bands['nir']} - {bands['red']}) / "
                    f"({bands['nir']} + 6 * {bands['red']} - 7.5 * {bands['blue']} + 1))"
                )
            case Indicator.NBR:
                return f"({bands['nir']} - {bands['swir']}) / ({bands['nir']} + {bands['swir']})"
            case _:
                raise ConfigurationError(
                    f"{indicator.value} is not a spectral index; use a dedicated product "
                    "(e.g. Hansen GFC for forest-area indicators)."
                )


class EarthEngineCovariateProvider:
    """Matching covariates from Earth Engine assets. NOT IMPLEMENTED.

    Planned assets: CHIRPS daily rainfall, SRTM elevation and derived slope,
    JRC Global Surface Water, WorldPop population density, and an OSM-derived
    distance-to-road raster.
    """

    name = "google-earth-engine"

    def covariates(self, area: AreaOfInterest) -> dict[str, float]:
        """Fetch covariates for an area. NOT IMPLEMENTED."""
        raise DataUnavailableError(
            "EarthEngineCovariateProvider.covariates is not implemented yet; "
            "use SyntheticCovariateProvider for offline runs."
        )
