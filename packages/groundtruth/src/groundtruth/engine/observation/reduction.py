"""The Earth-observation reduction methodology: from scenes to one number per year.

**Owner: Viraj.** This module decides *what is measured*: which collection,
which bands, how digital numbers become reflectance, which pixels are unusable,
how a year collapses to one value, and how many clear observations back it.
The platform's Earth Engine client (#22) decides *how it is fetched*:
authentication, retries, caching and pinning. The two meet at the
:class:`ReductionSpec` (coordination point C3). The spec is plain data and is
published through ``describe_engine()["reduction"]``, so the platform can read
it without importing engine internals.

The reference implementation :func:`reduce_period` performs the same chain on
numpy arrays. It is what the tests validate against known reflectance targets,
and what a platform client can check a small Earth Engine chip against.

The chain, per sensor, per calendar year:

1. **Reflectance.** ``rho = DN * scale + offset``, then pixels outside
   ``[0, 1]`` are masked. Index formulae (EVI's ``+1`` term in particular)
   assume reflectance, not digital numbers.
2. **Quality mask.** Sentinel-2: SCL classes in ``SCL_INVALID_CLASSES``.
   Landsat Collection 2: any of the QA_PIXEL fill, dilated-cloud, cirrus,
   cloud, cloud-shadow or snow bits, or any radiometric saturation.
3. **Index per scene, then the annual median.** The index is computed on each
   clear scene and the per-pixel median is taken across the year. Compositing
   bands first and computing the index afterwards would pair red from one date
   with NIR from another, producing a pixel that was never observed.
4. **Zonal reduction.** The zone value is the mean of the per-pixel annual
   medians over pixels with at least one clear scene. ``n_valid_observations``
   is the zone's median per-pixel clear-scene count, so a year resting on two
   scenes is visibly not the same measurement as one resting on twenty. The
   share of zone pixels with any clear scene is reported alongside.

Cross-sensor calibration across the Landsat/Sentinel boundary is #5; which
sensor serves which year is declared here (``SensorSpec.years``) but the
transition is not corrected here.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np

from groundtruth.contracts.errors import EstimationError
from groundtruth.contracts.types import Indicator
from groundtruth.engine.observation.indices import evi, nbr, ndvi
from groundtruth.engine.observation.masking import SCL_INVALID_CLASSES, scl_cloud_mask

REDUCTION_SCALE_M = 30
"""Reduction scale for every sensor: Landsat's native grid, so a Sentinel-2
year and a Landsat year describe the same ground footprint."""

LANDSAT_QA_INVALID_BITS: tuple[int, ...] = (
    0,  # fill
    1,  # dilated cloud
    2,  # cirrus (Landsat 8/9 only; always 0 on TM/ETM+)
    3,  # cloud
    4,  # cloud shadow
    5,  # snow
)
"""Collection 2 QA_PIXEL bits that make a pixel unusable."""


@dataclass(frozen=True)
class SensorSpec:
    """How one sensor's scenes become reflectance and a quality mask."""

    sensor: str
    collection: str
    bands: Mapping[str, str]
    """Role (red, nir, blue, swir2) to the collection's band name."""
    reflectance_scale: float
    reflectance_offset: float
    mask: str
    """``"scl"`` or ``"qa_pixel"``."""
    mask_band: str
    years: tuple[int, int | None]
    """First and last calendar year the sensor's archive covers; ``None`` is open."""
    notes: str = ""

    def covers(self, year: int) -> bool:
        """True if the sensor has an archive for ``year``."""
        first, last = self.years
        return first <= year and (last is None or year <= last)


_LANDSAT_SCALE = 0.0000275
_LANDSAT_OFFSET = -0.2

SENSORS: Mapping[str, SensorSpec] = {
    "sentinel2": SensorSpec(
        sensor="sentinel2",
        collection="COPERNICUS/S2_SR_HARMONIZED",
        bands={"blue": "B2", "red": "B4", "nir": "B8", "swir2": "B12"},
        reflectance_scale=1e-4,
        reflectance_offset=0.0,
        mask="scl",
        mask_band="SCL",
        years=(2017, None),
        notes=(
            "The harmonized collection already removes the +1000 DN offset introduced with "
            "processing baseline 04.00, so a single 1e-4 scale applies across the archive. "
            "Surface reflectance is complete globally from 2017."
        ),
    ),
    "landsat9": SensorSpec(
        sensor="landsat9",
        collection="LANDSAT/LC09/C02/T1_L2",
        bands={"blue": "SR_B2", "red": "SR_B4", "nir": "SR_B5", "swir2": "SR_B7"},
        reflectance_scale=_LANDSAT_SCALE,
        reflectance_offset=_LANDSAT_OFFSET,
        mask="qa_pixel",
        mask_band="QA_PIXEL",
        years=(2022, None),
    ),
    "landsat8": SensorSpec(
        sensor="landsat8",
        collection="LANDSAT/LC08/C02/T1_L2",
        bands={"blue": "SR_B2", "red": "SR_B4", "nir": "SR_B5", "swir2": "SR_B7"},
        reflectance_scale=_LANDSAT_SCALE,
        reflectance_offset=_LANDSAT_OFFSET,
        mask="qa_pixel",
        mask_band="QA_PIXEL",
        years=(2013, None),
    ),
    "landsat7": SensorSpec(
        sensor="landsat7",
        collection="LANDSAT/LE07/C02/T1_L2",
        bands={"blue": "SR_B1", "red": "SR_B3", "nir": "SR_B4", "swir2": "SR_B7"},
        reflectance_scale=_LANDSAT_SCALE,
        reflectance_offset=_LANDSAT_OFFSET,
        mask="qa_pixel",
        mask_band="QA_PIXEL",
        years=(1999, 2022),
        notes=(
            "The scan-line corrector failed on 2003-05-31. Later scenes have no-data stripes, "
            "masked as fill, which lowers per-pixel clear counts rather than biasing values."
        ),
    ),
    "landsat5": SensorSpec(
        sensor="landsat5",
        collection="LANDSAT/LT05/C02/T1_L2",
        bands={"blue": "SR_B1", "red": "SR_B3", "nir": "SR_B4", "swir2": "SR_B7"},
        reflectance_scale=_LANDSAT_SCALE,
        reflectance_offset=_LANDSAT_OFFSET,
        mask="qa_pixel",
        mask_band="QA_PIXEL",
        years=(1984, 2011),
    ),
}
"""Every sensor the reduction supports. NBR uses SWIR2 (~2.2 um), as in Key &
Benson's definition, not SWIR1."""


INDEX_BANDS: Mapping[Indicator, tuple[str, ...]] = {
    Indicator.NDVI: ("nir", "red"),
    Indicator.EVI: ("nir", "red", "blue"),
    Indicator.NBR: ("nir", "swir2"),
}
"""Band roles each spectral index needs."""


@dataclass(frozen=True)
class ReductionSpec:
    """Everything the platform needs to produce one indicator series from one sensor."""

    sensor: SensorSpec
    indicator: Indicator
    scale_m: int = REDUCTION_SCALE_M
    composite: str = "per-scene-index/annual-median"
    zonal_value: str = "mean-of-pixel-medians/clear-pixels-only"
    observation_count: str = "zonal-median-of-per-pixel-clear-scene-count"

    def as_dict(self) -> dict[str, Any]:
        """JSON-safe form, for ``describe_engine()`` and for provenance."""
        mask: dict[str, Any] = {"type": self.sensor.mask, "band": self.sensor.mask_band}
        if self.sensor.mask == "scl":
            mask["invalid_classes"] = list(SCL_INVALID_CLASSES)
        else:
            mask["invalid_bits"] = list(LANDSAT_QA_INVALID_BITS)
            mask["radiometric_saturation_band"] = "QA_RADSAT"
        return {
            "sensor": self.sensor.sensor,
            "collection": self.sensor.collection,
            "indicator": self.indicator.value,
            "bands": {role: self.sensor.bands[role] for role in INDEX_BANDS[self.indicator]},
            "reflectance": {
                "scale": self.sensor.reflectance_scale,
                "offset": self.sensor.reflectance_offset,
                "valid_range": [0.0, 1.0],
            },
            "mask": mask,
            "composite": self.composite,
            "period": "calendar-year",
            "zonal_value": self.zonal_value,
            "observation_count": self.observation_count,
            "scale_m": self.scale_m,
            "years": list(self.sensor.years),
        }


def reduction_spec(indicator: Indicator, sensor: str) -> ReductionSpec:
    """The reduction for one spectral indicator on one sensor.

    Raises:
        EstimationError: if the indicator is not a spectral index this module
            reduces, or the sensor is unknown.
    """
    if indicator not in INDEX_BANDS:
        raise EstimationError(f"{indicator.value} is not a spectral index reduced from scenes")
    if sensor not in SENSORS:
        raise EstimationError(f"unknown sensor {sensor!r}; known: {sorted(SENSORS)}")
    return ReductionSpec(sensor=SENSORS[sensor], indicator=indicator)


def sensors_for_year(year: int) -> tuple[str, ...]:
    """Sensors with an archive for ``year``, newest first."""
    return tuple(name for name, spec in SENSORS.items() if spec.covers(year))


def to_reflectance(dn: np.ndarray, sensor: SensorSpec) -> np.ndarray:
    """Digital numbers to surface reflectance; out-of-range pixels become NaN."""
    rho = np.asarray(dn, dtype=float) * sensor.reflectance_scale + sensor.reflectance_offset
    rho[(rho < 0.0) | (rho > 1.0)] = np.nan
    return rho


def qa_pixel_mask(
    qa_pixel: np.ndarray,
    radsat: np.ndarray | None = None,
    invalid_bits: tuple[int, ...] = LANDSAT_QA_INVALID_BITS,
) -> np.ndarray:
    """Boolean mask that is ``True`` for usable pixels in a Landsat C2 QA_PIXEL band."""
    qa = np.asarray(qa_pixel).astype(np.int64)
    bitmask = 0
    for bit in invalid_bits:
        bitmask |= 1 << bit
    usable = (qa & bitmask) == 0
    if radsat is not None:
        usable &= np.asarray(radsat).astype(np.int64) == 0
    return np.asarray(usable, dtype=bool)


def scene_index(indicator: Indicator, reflectance: Mapping[str, np.ndarray]) -> np.ndarray:
    """Compute a spectral index from per-role reflectance arrays."""
    match indicator:
        case Indicator.NDVI:
            return ndvi(reflectance["nir"], reflectance["red"])
        case Indicator.EVI:
            return evi(reflectance["nir"], reflectance["red"], reflectance["blue"])
        case Indicator.NBR:
            return nbr(reflectance["nir"], reflectance["swir2"])
        case _:
            raise EstimationError(f"{indicator.value} is not a spectral index")


@dataclass(frozen=True)
class PeriodReduction:
    """One zone, one year: the value and how much evidence backs it."""

    value: float
    n_valid_observations: int
    clear_pixel_fraction: float
    n_scenes: int


def reduce_period(
    spec: ReductionSpec,
    scenes_dn: Mapping[str, np.ndarray],
    quality: np.ndarray,
    zone: np.ndarray,
    *,
    radsat: np.ndarray | None = None,
) -> PeriodReduction:
    """Reference implementation of the chain for one zone and one calendar year.

    Args:
        spec: The reduction to apply.
        scenes_dn: Band role to a ``(n_scenes, h, w)`` stack of digital numbers.
        quality: ``(n_scenes, h, w)`` SCL classes or QA_PIXEL values.
        zone: ``(h, w)`` boolean mask of pixels inside the unit.
        radsat: Optional ``(n_scenes, h, w)`` QA_RADSAT values (Landsat).

    Returns:
        A :class:`PeriodReduction`. A year with no clear pixel in the zone has
        a NaN value and zero observations; it is reported, not filled.
    """
    roles = INDEX_BANDS[spec.indicator]
    missing = [r for r in roles if r not in scenes_dn]
    if missing:
        raise EstimationError(f"{spec.indicator.value} needs bands {missing}")
    shapes = {np.asarray(scenes_dn[r]).shape for r in roles} | {np.asarray(quality).shape}
    if len(shapes) != 1:
        raise EstimationError("every band stack and the quality stack must share one shape")
    n_scenes = np.asarray(quality).shape[0]
    zone_mask = np.asarray(zone, dtype=bool)

    if spec.sensor.mask == "scl":
        usable = scl_cloud_mask(quality)
    else:
        usable = qa_pixel_mask(quality, radsat)

    reflectance = {r: to_reflectance(scenes_dn[r], spec.sensor) for r in roles}
    index = scene_index(spec.indicator, reflectance)
    index[~usable] = np.nan

    clear_counts = np.sum(~np.isnan(index), axis=0)
    with np.errstate(all="ignore"):
        pixel_medians = (
            np.nanmedian(index, axis=0) if n_scenes else np.full(zone_mask.shape, np.nan)
        )

    in_zone = zone_mask.sum()
    if in_zone == 0:
        raise EstimationError("the zone contains no pixels")
    zone_clear = zone_mask & (clear_counts > 0)
    value = float(np.mean(pixel_medians[zone_clear])) if zone_clear.any() else float("nan")
    return PeriodReduction(
        value=value,
        n_valid_observations=int(np.median(clear_counts[zone_mask])),
        clear_pixel_fraction=float(zone_clear.sum() / in_zone),
        n_scenes=int(n_scenes),
    )


def describe_reduction() -> dict[str, Any]:
    """Every supported (sensor, indicator) reduction as plain data."""
    return {
        "scale_m": REDUCTION_SCALE_M,
        "specs": [
            reduction_spec(indicator, sensor).as_dict()
            for sensor in SENSORS
            for indicator in INDEX_BANDS
        ],
        "not_reduced_here": ["tree_cover_fraction", "forest_area_ha"],
    }


__all__ = [
    "INDEX_BANDS",
    "LANDSAT_QA_INVALID_BITS",
    "REDUCTION_SCALE_M",
    "SENSORS",
    "PeriodReduction",
    "ReductionSpec",
    "SensorSpec",
    "describe_reduction",
    "qa_pixel_mask",
    "reduce_period",
    "reduction_spec",
    "scene_index",
    "sensors_for_year",
    "to_reflectance",
]
