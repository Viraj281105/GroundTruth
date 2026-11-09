"""The real Earth Engine backend for unit construction and covariates.

**Owner: Bhumi** (#23). Everything here is one Earth Engine request, kept thin:
the rules live in :mod:`groundtruth.platform.units`, retries and sign-in in
:mod:`~groundtruth.platform.datasets.session`, caching in the services above.

Offline tests drive this code with a recording stand-in for the ``ee`` module, which
checks the calls it makes; only the network tests can check what Earth Engine does
with them.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from groundtruth.platform.datasets.covariates import (
    MASK_RULE_CENTRE,
    MASK_RULE_FRACTION,
    CovariateQuery,
)
from groundtruth.platform.datasets.earthengine import MAX_PIXELS, TILE_SCALE, EarthEngineApiBackend
from groundtruth.platform.datasets.ee_mask import adr011_mask, forest_images, protected_areas
from groundtruth.platform.datasets.resilience import PermanentError

COARSE_MASK_MAX_PIXELS = 65_536
"""``reduceResolution``'s input limit. A CHIRPS pixel holds about 34,000 mask pixels."""

WORLDPOP_COUNTRY_PROPERTY = "country"


@dataclass(frozen=True)
class MaskQuery:
    """One outline and the recipe of the mask applied inside it."""

    outline: Mapping[str, Any]
    recipe: Mapping[str, Any]


class EarthEngineUnitApiBackend(EarthEngineApiBackend):
    """Observations (#22), plus the requests unit construction and covariates need."""

    def _grid_args(self, region: Any, recipe: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "geometry": region,
            "crs": recipe["crs"],
            "scale": float(recipe["scale_m"]),
            "maxPixels": MAX_PIXELS,
            "tileScale": TILE_SCALE,
            "bestEffort": False,
        }

    # --- listings: names only, never a count of anything --------------------------

    def list_ecoregion_names(self, asset: str, bounds: Sequence[float]) -> list[str]:
        ee = self.ee
        names: list[str] = (
            ee.FeatureCollection(asset)
            .filterBounds(ee.Geometry.Rectangle(list(bounds)))
            .aggregate_array("ECO_NAME")
            .distinct()
            .getInfo()
        )
        return sorted(names)

    def list_wdpa_releases(self, folder: str) -> list[str]:
        listed = self.ee.data.listAssets({"parent": folder})
        return sorted(str(entry.get("id") or entry.get("name")) for entry in listed["assets"])

    def list_wdpa_statuses(self, asset: str, bounds: Sequence[float]) -> list[str]:
        ee = self.ee
        statuses: list[str] = (
            ee.FeatureCollection(asset)
            .filterBounds(ee.Geometry.Rectangle(list(bounds)))
            .aggregate_array("STATUS")
            .distinct()
            .getInfo()
        )
        return sorted(statuses)

    def list_admin_countries(self, asset: str, bounds: Sequence[float]) -> list[str]:
        ee = self.ee
        names: list[str] = (
            ee.FeatureCollection(asset)
            .filterBounds(ee.Geometry.Rectangle(list(bounds)))
            .aggregate_array("ADM0_NAME")
            .distinct()
            .getInfo()
        )
        return sorted(names)

    def list_worldpop_countries(self, asset: str, year: int, bounds: Sequence[float]) -> list[str]:
        ee = self.ee
        countries: list[str] = (
            ee.ImageCollection(asset)
            .filter(ee.Filter.eq("year", year))
            .filterBounds(ee.Geometry.Rectangle(list(bounds)))
            .aggregate_array(WORLDPOP_COUNTRY_PROPERTY)
            .distinct()
            .getInfo()
        )
        return sorted(countries)

    # --- districts and the belt ----------------------------------------------------

    def list_districts(self, asset: str, adm0_names: Sequence[str]) -> list[dict[str, Any]]:
        ee = self.ee
        districts = ee.FeatureCollection(asset).filter(
            ee.Filter.inList("ADM0_NAME", list(adm0_names))
        )
        listed = ee.Dictionary(
            {
                "codes": districts.aggregate_array("ADM2_CODE"),
                "countries": districts.aggregate_array("ADM0_NAME"),
            }
        ).getInfo()
        return [
            {"adm2_code": code, "adm0_name": country}
            for code, country in zip(listed["codes"], listed["countries"], strict=True)
        ]

    def district_outline(self, asset: str, adm2_code: int | str) -> dict[str, Any]:
        ee = self.ee
        district = ee.Feature(
            ee.FeatureCollection(asset).filter(ee.Filter.eq("ADM2_CODE", int(adm2_code))).first()
        )
        geometry: dict[str, Any] = district.geometry().getInfo()
        if geometry.get("type") not in ("Polygon", "MultiPolygon"):
            raise PermanentError(
                f"GAUL district {adm2_code} has an unusable geometry type {geometry.get('type')!r}"
            )
        return {"type": geometry["type"], "coordinates": geometry["coordinates"]}

    def leakage_belt(
        self, boundary: Mapping[str, Any], radius_m: float, max_error_m: float, crs: str
    ) -> dict[str, Any]:
        """The outward buffer of the **unmasked** registry boundary, as ADR-011 requires."""
        ee = self.ee
        region = ee.Geometry(dict(boundary), None, True, False)
        belt: dict[str, Any] = region.buffer(radius_m, max_error_m, crs).getInfo()
        return belt

    def districts_in_belt(
        self, asset: str, adm0_names: Sequence[str], belt: Mapping[str, Any]
    ) -> list[Any]:
        ee = self.ee
        codes: list[Any] = (
            ee.FeatureCollection(asset)
            .filter(ee.Filter.inList("ADM0_NAME", list(adm0_names)))
            .filterBounds(ee.Geometry(dict(belt), None, True, False))
            .aggregate_array("ADM2_CODE")
            .getInfo()
        )
        return codes

    # --- measurements ---------------------------------------------------------------

    def measure_forest(self, query: MaskQuery) -> dict[str, Any]:
        """Pixel counts behind the >=50% ecoregion rule, before any subtraction."""
        ee = self.ee
        region = ee.Geometry(dict(query.outline), None, True, False)
        forest, in_ecoregions = forest_images(ee, region, query.recipe)
        args = self._grid_args(region, query.recipe)
        reducer = ee.Reducer.sum().unweighted()
        result: dict[str, Any] = ee.Dictionary(
            {
                "forest": forest.rename("v").reduceRegion(reducer=reducer, **args).get("v"),
                "forest_in_ecoregions": in_ecoregions.rename("v")
                .reduceRegion(reducer=reducer, **args)
                .get("v"),
            }
        ).getInfo()
        return result

    def measure_mask(self, query: MaskQuery) -> dict[str, Any]:
        """Eligible pixels, and how many of them are protected (which must be none)."""
        ee = self.ee
        region = ee.Geometry(dict(query.outline), None, True, False)
        mask = adr011_mask(ee, region, query.recipe)
        protected = (
            ee.Image.constant(0)
            .byte()
            .paint(protected_areas(ee, query.recipe["protected_areas"]), 1)
        )
        args = self._grid_args(region, query.recipe)
        reducer = ee.Reducer.sum().unweighted()
        result: dict[str, Any] = ee.Dictionary(
            {
                "eligible": mask.rename("v").reduceRegion(reducer=reducer, **args).get("v"),
                "protected_overlap": mask.And(protected)
                .rename("v")
                .reduceRegion(reducer=reducer, **args)
                .get("v"),
            }
        ).getInfo()
        return result

    def count_fragments(self, query: MaskQuery) -> int:
        """Connected components of the eligible mask. Recorded; never drops or splits a unit."""
        ee = self.ee
        region = ee.Geometry(dict(query.outline), None, True, False)
        mask = adr011_mask(ee, region, query.recipe).selfMask()
        count: int = (
            mask.reduceToVectors(
                geometry=region,
                crs=query.recipe["crs"],
                scale=float(query.recipe["scale_m"]),
                geometryType="bb",
                eightConnected=True,
                maxPixels=MAX_PIXELS,
                tileScale=TILE_SCALE,
                bestEffort=False,
            )
            .size()
            .getInfo()
        )
        return count

    # --- covariates -------------------------------------------------------------------

    def _covariate_image(self, query: CovariateQuery, region: Any) -> tuple[Any, Any]:
        """The covariate as an image, and the projection native to its dataset."""
        ee = self.ee
        covariate = query.covariate
        kind = covariate["kind"]
        if kind == "mean-annual-total":
            first, last = int(covariate["first_year"]), int(covariate["last_year"])
            days = (
                ee.ImageCollection(covariate["asset"])
                .select(covariate["band"])
                .filterDate(f"{first}-01-01", f"{last + 1}-01-01")
            )
            total = days.sum().divide(last - first + 1)
            return total, ee.Image(days.first()).projection()
        if kind == "elevation":
            image = ee.Image(covariate["asset"]).select(covariate["band"])
            return image, image.projection()
        if kind == "slope":
            image = ee.Image(covariate["asset"]).select(covariate["band"])
            return ee.Terrain.slope(image), image.projection()
        if kind == "population-count":
            images = (
                ee.ImageCollection(covariate["asset"])
                .filter(ee.Filter.eq("year", int(covariate["year"])))
                .filterBounds(region)
                .select(covariate["band"])
            )
            return images.mosaic(), ee.Image(images.first()).projection()
        if kind == "distance-to-road":
            radius_m = float(covariate["search_radius_km"]) * 1000.0
            scale = float(covariate["scale_m"])
            roads = ee.FeatureCollection(covariate["asset"]).filterBounds(
                region.buffer(radius_m, scale)
            )
            distance_km = roads.distance(searchRadius=radius_m, maxError=scale).divide(1000.0)
            return distance_km, ee.Projection(query.recipe["crs"]).atScale(scale)
        raise PermanentError(f"no Earth Engine translation for covariate kind {kind!r}")

    def reduce_covariate(self, query: CovariateQuery) -> dict[str, Any]:
        """One covariate over the masked unit, at the dataset's native scale (V4)."""
        ee = self.ee
        region = ee.Geometry(dict(query.outline), None, True, False)
        image, projection = self._covariate_image(query, region)
        mask = adr011_mask(ee, region, query.recipe)
        statistic = query.covariate["statistic"]
        if statistic == "mean":
            reducer = ee.Reducer.mean()
        elif statistic == "sum":
            reducer = ee.Reducer.sum()
        else:
            raise PermanentError(f"unknown covariate statistic {statistic!r}")

        if query.mask_rule == MASK_RULE_FRACTION:
            # The share of each native pixel that is eligible. Earth Engine's weighted
            # reducers use a fractional mask as the pixel's weight.
            share = mask.reduceResolution(
                reducer=ee.Reducer.mean(), maxPixels=COARSE_MASK_MAX_PIXELS
            ).reproject(projection)
            masked = image.updateMask(share)
        elif query.mask_rule == MASK_RULE_CENTRE:
            masked = image.updateMask(mask.reproject(projection))
            reducer = reducer.unweighted()
        else:
            raise PermanentError(f"unknown native-scale mask rule {query.mask_rule!r}")

        common = {
            "geometry": region,
            "crs": projection,
            "maxPixels": MAX_PIXELS,
            "tileScale": TILE_SCALE,
            "bestEffort": False,
        }
        # Whole reduceRegion dictionaries rather than ``.get("v")``: a mean over no pixel
        # is null, and null values must come back as null rather than fail the request.
        values = {"value": masked.rename("v").reduceRegion(reducer=reducer, **common)}
        if query.covariate["kind"] == "distance-to-road":
            # The distance image is masked beyond the search radius, so a mean would
            # silently leave out the most remote pixels. Count them instead.
            beyond = image.unmask(-1).lt(0).And(mask.reproject(projection))
            values["unreachable_pixels"] = beyond.rename("v").reduceRegion(
                reducer=ee.Reducer.sum().unweighted(), **common
            )
        result: dict[str, Any] = ee.Dictionary(values).getInfo()
        return {name: (reduced or {}).get("v") for name, reduced in result.items()}


__all__ = ["EarthEngineUnitApiBackend", "MaskQuery"]
