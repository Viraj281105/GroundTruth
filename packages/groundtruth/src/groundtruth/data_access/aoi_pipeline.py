"""Genuine AOI-to-observation reduction pipeline and provenance-aware disk cache.

Connects GeoJSON Area-of-Interest (AOI) validation, STAC scene descriptors,
band reflectance scaling, cloud/shadow quality masking (Sentinel-2 SCL and
Landsat Collection 2 QA_PIXEL), spectral index calculation, and zonal median/mean
reduction into an auditable :class:`AOIObservationBundle`.

Cloud-starved or empty years are never interpolated or fabricated: they yield
``NaN`` with ``n_valid_observations = 0``.
"""

from __future__ import annotations

import json
import math
import re
import warnings
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import numpy as np

from groundtruth.contracts.errors import DataUnavailableError
from groundtruth.contracts.provenance import Provenance
from groundtruth.contracts.types import INDICATOR_UNITS, Indicator, TimeSeries
from groundtruth.data_access.stac import (
    DEFAULT_STAC_URL,
    RasterGridSpec,
    SceneDescriptor,
    _extract_geojson_geometry,
    build_aoi_raster_grid,
    fetch_scene_raster_data,
    open_stac_client,
    scenes_hash,
    search_scenes,
    validate_aoi_geojson,
)
from groundtruth.engine.observation.indices import evi, nbr, ndmi, ndvi, savi
from groundtruth.engine.observation.masking import SCL_INVALID_CLASSES, scl_cloud_mask
from groundtruth.engine.observation.reduction import (
    SENSORS,
    SensorSpec,
    qa_pixel_mask,
    to_reflectance,
)
from groundtruth.engine.observation.zonal import zonal_stats


class DataOrigin(StrEnum):
    """Lineage classification for an observation bundle."""

    REAL_STAC = "real_stac"
    CACHED_REAL_STAC = "cached_real_stac"
    SYNTHETIC = "synthetic"


_SENSOR_ALIASES: dict[str, str] = {
    "sentinel-2": "sentinel2",
    "sentinel-2-l2a": "sentinel2",
    "s2": "sentinel2",
    "landsat-9": "landsat9",
    "landsat-8": "landsat8",
    "landsat-7": "landsat7",
    "landsat-5": "landsat5",
    "landsat": "landsat8",
}

_SUPPORTED_INDICATORS: dict[str, tuple[str, ...]] = {
    "ndvi": ("nir", "red"),
    "evi": ("nir", "red", "blue"),
    "nbr": ("nir", "swir2"),
    "ndmi": ("nir", "swir1"),
    "savi": ("nir", "red"),
}

_ROLE_BAND_ALIASES: dict[str, dict[str, tuple[str, ...]]] = {
    "sentinel2": {
        "blue": ("blue", "B2", "B02"),
        "red": ("red", "B4", "B04"),
        "nir": ("nir", "B8", "B08", "B8A"),
        "swir1": ("swir1", "B11"),
        "swir2": ("swir2", "B12"),
    },
    "landsat9": {
        "blue": ("blue", "SR_B2", "B2"),
        "red": ("red", "SR_B4", "B4"),
        "nir": ("nir", "SR_B5", "B5", "nir08"),
        "swir1": ("swir1", "SR_B6", "B6", "swir16"),
        "swir2": ("swir2", "SR_B7", "B7", "swir22"),
    },
    "landsat8": {
        "blue": ("blue", "SR_B2", "B2"),
        "red": ("red", "SR_B4", "B4"),
        "nir": ("nir", "SR_B5", "B5", "nir08"),
        "swir1": ("swir1", "SR_B6", "B6", "swir16"),
        "swir2": ("swir2", "SR_B7", "B7", "swir22"),
    },
    "landsat7": {
        "blue": ("blue", "SR_B1", "B1"),
        "red": ("red", "SR_B3", "B3"),
        "nir": ("nir", "SR_B4", "B4", "nir08"),
        "swir1": ("swir1", "SR_B5", "B5", "swir16"),
        "swir2": ("swir2", "SR_B7", "B7", "swir22"),
    },
    "landsat5": {
        "blue": ("blue", "SR_B1", "B1"),
        "red": ("red", "SR_B3", "B3"),
        "nir": ("nir", "SR_B4", "B4", "nir08"),
        "swir1": ("swir1", "SR_B5", "B5", "swir16"),
        "swir2": ("swir2", "SR_B7", "B7", "swir22"),
    },
}


@dataclass(frozen=True)
class SceneRasterChip:
    """In-memory digital-number band arrays and quality layer for one STAC scene."""

    descriptor: SceneDescriptor
    bands_dn: Mapping[str, np.ndarray]
    quality: np.ndarray
    radsat: np.ndarray | None = None


@dataclass(frozen=True)
class AnnualObservationRecord:
    """Auditable annual observation summary for one AOI and one calendar year."""

    year: int
    indicator: str
    value: float
    n_valid_observations: int
    clear_pixel_fraction: float
    n_scenes: int
    scene_ids: tuple[str, ...]
    acquisition_dates: tuple[str, ...]
    sensor: str
    scenes_sha256: str
    cloud_cover_mean: float | None = None
    scene_cloud_cover: tuple[float | None, ...] = ()
    n_valid_pixels: int | None = None
    n_total_pixels: int | None = None
    n_masked_pixels: int | None = None
    indices: Mapping[str, float] | None = None
    processing_metadata: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        serialized_indices: dict[str, float | None] | None = None
        if self.indices is not None:
            serialized_indices = {
                k: (None if math.isnan(v) else float(v))
                for k, v in self.indices.items()
            }
        return {
            "year": self.year,
            "indicator": self.indicator,
            "value": None if math.isnan(self.value) else self.value,
            "n_valid_observations": self.n_valid_observations,
            "clear_pixel_fraction": self.clear_pixel_fraction,
            "n_scenes": self.n_scenes,
            "scene_ids": list(self.scene_ids),
            "acquisition_dates": list(self.acquisition_dates),
            "sensor": self.sensor,
            "scenes_sha256": self.scenes_sha256,
            "cloud_cover_mean": self.cloud_cover_mean,
            "scene_cloud_cover": list(self.scene_cloud_cover),
            "n_valid_pixels": self.n_valid_pixels,
            "n_total_pixels": self.n_total_pixels,
            "n_masked_pixels": self.n_masked_pixels,
            "indices": serialized_indices,
            "processing_metadata": (
                dict(self.processing_metadata)
                if self.processing_metadata is not None
                else None
            ),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> AnnualObservationRecord:
        """Deserialize from a dictionary."""
        raw_val = data.get("value")
        val = float("nan") if raw_val is None else float(raw_val)
        raw_indices = data.get("indices")
        parsed_indices: dict[str, float] | None = None
        if isinstance(raw_indices, Mapping):
            parsed_indices = {
                str(k): (float("nan") if v is None else float(v))
                for k, v in raw_indices.items()
            }
        raw_cc = data.get("scene_cloud_cover")
        scene_cc: tuple[float | None, ...] = ()
        if isinstance(raw_cc, Sequence) and not isinstance(raw_cc, (str, bytes)):
            scene_cc = tuple(None if c is None else float(c) for c in raw_cc)
        raw_meta = data.get("processing_metadata")
        return cls(
            year=int(data["year"]),
            indicator=str(data["indicator"]),
            value=val,
            n_valid_observations=int(data["n_valid_observations"]),
            clear_pixel_fraction=float(data["clear_pixel_fraction"]),
            n_scenes=int(data["n_scenes"]),
            scene_ids=tuple(str(s) for s in data["scene_ids"]),
            acquisition_dates=tuple(str(d) for d in data["acquisition_dates"]),
            sensor=str(data["sensor"]),
            scenes_sha256=str(data["scenes_sha256"]),
            cloud_cover_mean=(
                None if data.get("cloud_cover_mean") is None else float(data["cloud_cover_mean"])
            ),
            scene_cloud_cover=scene_cc,
            n_valid_pixels=(
                None if data.get("n_valid_pixels") is None else int(data["n_valid_pixels"])
            ),
            n_total_pixels=(
                None if data.get("n_total_pixels") is None else int(data["n_total_pixels"])
            ),
            n_masked_pixels=(
                None if data.get("n_masked_pixels") is None else int(data["n_masked_pixels"])
            ),
            indices=parsed_indices,
            processing_metadata=dict(raw_meta) if isinstance(raw_meta, Mapping) else None,
        )


@dataclass(frozen=True)
class AOIObservationBundle:
    """Complete multi-year observation bundle for one geographical unit (AOI)."""

    unit_id: str
    indicator: str
    bbox: tuple[float, float, float, float]
    records: tuple[AnnualObservationRecord, ...]
    data_origin: DataOrigin
    catalog_url: str | None
    provenance: Provenance

    @property
    def is_synthetic(self) -> bool:
        """True if this bundle came from synthetic data rather than real STAC imagery."""
        return self.data_origin == DataOrigin.SYNTHETIC

    def to_time_series(self, *, drop_nan: bool = False) -> TimeSeries:
        """Convert the observation records into a contract :class:`TimeSeries`.

        Args:
            drop_nan: If ``True``, drop cloud-starved years whose ``value`` is ``NaN``.
                If ``False`` (default), retain all years with their ``NaN`` value and
                ``n_valid_observations = 0`` so downstream stages can inspect or refuse
                sparse periods.
        """
        ordered = sorted(self.records, key=lambda r: r.year)
        if drop_nan:
            ordered = [r for r in ordered if not math.isnan(r.value)]
        if self.indicator in Indicator._value2member_map_:
            ind_enum = Indicator(self.indicator)
            unit_str = INDICATOR_UNITS[ind_enum]
        else:
            ind_enum = Indicator.NDVI
            unit_str = self.indicator
        return TimeSeries(
            unit_id=self.unit_id,
            indicator=ind_enum,
            periods=tuple(r.year for r in ordered),
            values=tuple(r.value for r in ordered),
            unit=unit_str,
            n_valid_observations=tuple(r.n_valid_observations for r in ordered),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize bundle to a JSON-compatible dictionary."""
        return {
            "unit_id": self.unit_id,
            "indicator": self.indicator,
            "bbox": list(self.bbox),
            "records": [r.to_dict() for r in self.records],
            "data_origin": self.data_origin.value,
            "catalog_url": self.catalog_url,
            "provenance": self.provenance.model_dump(mode="json"),
        }

    @classmethod
    def from_dict(
        cls,
        data: Mapping[str, Any],
        *,
        override_origin: DataOrigin | None = None,
    ) -> AOIObservationBundle:
        """Deserialize bundle from a JSON dictionary."""
        raw_bbox = [float(v) for v in data["bbox"]]
        if len(raw_bbox) != 4:
            raise ValueError(f"Invalid bbox in cached bundle: {raw_bbox!r}")
        origin = override_origin or DataOrigin(str(data["data_origin"]))
        prov = Provenance.model_validate(data["provenance"])
        if override_origin is not None and override_origin != DataOrigin(str(data["data_origin"])):
            updated_params = dict(prov.parameters)
            updated_params["cached_from_origin"] = str(data["data_origin"])
            updated_params["effective_data_origin"] = override_origin.value
            prov = prov.model_copy(update={"parameters": updated_params})
        return cls(
            unit_id=str(data["unit_id"]),
            indicator=str(data["indicator"]),
            bbox=(raw_bbox[0], raw_bbox[1], raw_bbox[2], raw_bbox[3]),
            records=tuple(AnnualObservationRecord.from_dict(r) for r in data["records"]),
            data_origin=origin,
            catalog_url=None if data.get("catalog_url") is None else str(data["catalog_url"]),
            provenance=prov,
        )


def _resolve_sensor(sensor: str) -> SensorSpec:
    key = _SENSOR_ALIASES.get(sensor.lower(), sensor.lower())
    if key not in SENSORS:
        raise ValueError(f"Unknown sensor {sensor!r}; supported sensors: {sorted(SENSORS)}")
    return SENSORS[key]


def _resolve_indicator(indicator: str | Indicator) -> str:
    ind = indicator.value if isinstance(indicator, Indicator) else str(indicator).lower()
    if ind not in _SUPPORTED_INDICATORS:
        raise ValueError(
            f"Unsupported spectral indicator {indicator!r}; "
            f"supported: {sorted(_SUPPORTED_INDICATORS)}"
        )
    return ind


def _has_role_band(chip: SceneRasterChip, role: str, sensor_key: str) -> bool:
    candidates = _ROLE_BAND_ALIASES.get(sensor_key, {}).get(role, (role,))
    return any(name in chip.bands_dn for name in candidates)


def _extract_role_band(
    chip: SceneRasterChip,
    role: str,
    sensor_key: str,
) -> np.ndarray:
    candidates = _ROLE_BAND_ALIASES.get(sensor_key, {}).get(role, (role,))
    for name in candidates:
        if name in chip.bands_dn:
            return np.asarray(chip.bands_dn[name], dtype=float)
    raise ValueError(
        f"Scene {chip.descriptor.id!r} is missing band for role {role!r} "
        f"(tried {candidates}; available: {sorted(chip.bands_dn)})"
    )


def _compute_index(indicator: str, reflectance: Mapping[str, np.ndarray]) -> np.ndarray:
    match indicator:
        case "ndvi":
            return ndvi(reflectance["nir"], reflectance["red"])
        case "evi":
            return evi(reflectance["nir"], reflectance["red"], reflectance["blue"])
        case "nbr":
            return nbr(reflectance["nir"], reflectance["swir2"])
        case "ndmi":
            return ndmi(reflectance["nir"], reflectance["swir1"])
        case "savi":
            return savi(reflectance["nir"], reflectance["red"])
        case _:
            raise ValueError(f"Unsupported indicator: {indicator!r}")


_CORE_VEGETATION_INDICES: tuple[str, ...] = ("ndvi", "evi", "ndmi", "nbr")


def _safe_float_or_none(val: float) -> float | None:
    return None if math.isnan(val) else float(val)


def reduce_aoi_scenes_to_series(
    unit_id: str,
    aoi_geojson: dict[str, Any],
    chips_by_year: Mapping[int, Sequence[SceneRasterChip]],
    indicator: str | Indicator = "ndvi",
    sensor: str = "sentinel2",
    zone_mask: np.ndarray | None = None,
    data_origin: DataOrigin = DataOrigin.REAL_STAC,
    catalog_url: str | None = DEFAULT_STAC_URL,
) -> AOIObservationBundle:
    """Reduce multi-year STAC raster chips over an AOI into an :class:`AOIObservationBundle`.

    Applies GeoJSON validation, reflectance scaling, sensor-specific cloud/shadow
    masking (Sentinel-2 SCL or Landsat QA_PIXEL), per-scene spectral index computation,
    per-pixel annual median compositing, and zonal mean reduction over clear pixels.
    Automatically calculates NDVI, EVI, NDMI, and NBR wherever the required bands
    are present on the scene chips.
    """
    if not unit_id or not unit_id.strip():
        raise ValueError("unit_id must be a non-empty string")
    bbox = validate_aoi_geojson(aoi_geojson)
    ind_name = _resolve_indicator(indicator)
    sensor_spec = _resolve_sensor(sensor)
    required_roles = _SUPPORTED_INDICATORS[ind_name]

    explicit_zone: np.ndarray | None = None
    if zone_mask is not None:
        explicit_zone = np.asarray(zone_mask, dtype=bool)
        if explicit_zone.ndim != 2:
            raise ValueError(f"zone_mask must be 2D (h, w), got shape {explicit_zone.shape}")
        if not explicit_zone.any():
            raise ValueError("zone_mask contains no True pixels")

    records: list[AnnualObservationRecord] = []
    all_descriptors: list[SceneDescriptor] = []

    for year in sorted(chips_by_year):
        chips = list(chips_by_year[year])
        if not chips:
            n_tot = int(explicit_zone.sum()) if explicit_zone is not None else 0
            records.append(
                AnnualObservationRecord(
                    year=int(year),
                    indicator=ind_name,
                    value=float("nan"),
                    n_valid_observations=0,
                    clear_pixel_fraction=0.0,
                    n_scenes=0,
                    scene_ids=(),
                    acquisition_dates=(),
                    sensor=sensor_spec.sensor,
                    scenes_sha256=scenes_hash(()),
                    cloud_cover_mean=None,
                    scene_cloud_cover=(),
                    n_valid_pixels=0,
                    n_total_pixels=n_tot,
                    n_masked_pixels=n_tot,
                    indices={ind_name: float("nan")},
                    processing_metadata={
                        "n_total_zone_pixels": n_tot,
                        "n_valid_zone_pixels": 0,
                        "n_masked_zone_pixels": n_tot,
                        "mask_type": sensor_spec.mask,
                        "scene_masking": [],
                    },
                )
            )
            continue

        first_q = np.asarray(chips[0].quality)
        if first_q.ndim != 2:
            raise ValueError(f"Scene quality array must be 2D (h, w), got {first_q.shape}")
        chip_shape = first_q.shape

        year_zone = (
            explicit_zone
            if explicit_zone is not None
            else np.ones(chip_shape, dtype=bool)
        )
        if year_zone.shape != chip_shape:
            raise ValueError(
                f"zone_mask shape {year_zone.shape} does not match chip shape {chip_shape}"
            )

        # Determine all band roles available across all chips in this year so we can
        # calculate NDVI, EVI, NDMI, and NBR wherever their required bands exist.
        all_candidate_roles = ("nir", "red", "blue", "swir1", "swir2")
        available_optional_roles = tuple(
            r
            for r in all_candidate_roles
            if r not in required_roles
            and all(_has_role_band(c, r, sensor_spec.sensor) for c in chips)
        )
        roles_to_extract = tuple(dict.fromkeys((*required_roles, *available_optional_roles)))

        quality_list: list[np.ndarray] = []
        radsat_list: list[np.ndarray] = []
        has_radsat = any(c.radsat is not None for c in chips)
        role_stacks: dict[str, list[np.ndarray]] = {r: [] for r in roles_to_extract}

        for chip in chips:
            q_arr = np.asarray(chip.quality)
            if q_arr.shape != chip_shape:
                raise ValueError(
                    f"Scene {chip.descriptor.id!r} quality shape {q_arr.shape} != {chip_shape}"
                )
            quality_list.append(q_arr)
            if has_radsat:
                if chip.radsat is None:
                    radsat_list.append(np.zeros(chip_shape, dtype=np.int64))
                else:
                    r_arr = np.asarray(chip.radsat)
                    if r_arr.shape != chip_shape:
                        raise ValueError(
                            f"Scene {chip.descriptor.id!r} radsat shape "
                            f"{r_arr.shape} != {chip_shape}"
                        )
                    radsat_list.append(r_arr)
            for role in roles_to_extract:
                b_arr = _extract_role_band(chip, role, sensor_spec.sensor)
                if b_arr.shape != chip_shape:
                    raise ValueError(
                        f"Scene {chip.descriptor.id!r} band {role!r} shape "
                        f"{b_arr.shape} != {chip_shape}"
                    )
                role_stacks[role].append(b_arr)

        quality_stack = np.stack(quality_list, axis=0)
        radsat_stack = np.stack(radsat_list, axis=0) if has_radsat else None

        if sensor_spec.mask == "scl":
            usable = scl_cloud_mask(quality_stack)
        else:
            usable = qa_pixel_mask(quality_stack, radsat_stack)

        reflectance = {
            role: to_reflectance(np.stack(role_stacks[role], axis=0), sensor_spec)
            for role in roles_to_extract
        }
        scene_idx = _compute_index(ind_name, reflectance)
        scene_idx[~usable] = np.nan

        clear_counts = np.sum(~np.isnan(scene_idx), axis=0)
        with warnings.catch_warnings(), np.errstate(all="ignore"):
            warnings.simplefilter("ignore", RuntimeWarning)
            pixel_medians = np.nanmedian(scene_idx, axis=0)

        in_zone = int(year_zone.sum())
        zone_clear = year_zone & (clear_counts > 0)
        n_valid_px = int(zone_clear.sum())
        n_masked_px = int(in_zone - n_valid_px)
        value = float(np.mean(pixel_medians[zone_clear])) if zone_clear.any() else float("nan")
        n_valid_obs = int(np.median(clear_counts[year_zone]))
        clear_frac = float(n_valid_px / in_zone)

        # Calculate NDVI, EVI, NDMI, NBR wherever required bands are present
        calculated_indices: dict[str, float] = {ind_name: value}
        for candidate_ind in _CORE_VEGETATION_INDICES:
            if candidate_ind == ind_name:
                continue
            cand_roles = _SUPPORTED_INDICATORS[candidate_ind]
            if all(r in reflectance for r in cand_roles):
                cand_scene_idx = _compute_index(candidate_ind, reflectance)
                cand_scene_idx[~usable] = np.nan
                cand_clear_counts = np.sum(~np.isnan(cand_scene_idx), axis=0)
                with warnings.catch_warnings(), np.errstate(all="ignore"):
                    warnings.simplefilter("ignore", RuntimeWarning)
                    cand_medians = np.nanmedian(cand_scene_idx, axis=0)
                cand_zone_clear = year_zone & (cand_clear_counts > 0)
                calculated_indices[candidate_ind] = (
                    float(np.mean(cand_medians[cand_zone_clear]))
                    if cand_zone_clear.any()
                    else float("nan")
                )

        # Per-scene cloud & shadow masking diagnostics within the AOI zone
        scene_masking_details: list[dict[str, Any]] = []
        for s_idx, chip in enumerate(chips):
            q_scene = quality_stack[s_idx][year_zone]
            u_scene = usable[s_idx][year_zone]
            idx_scene_valid = ~np.isnan(scene_idx[s_idx][year_zone])
            valid_px_scene = int(idx_scene_valid.sum())
            masked_px_scene = int(in_zone - valid_px_scene)
            detail: dict[str, Any] = {
                "scene_id": chip.descriptor.id,
                "datetime": chip.descriptor.datetime,
                "sensor": chip.descriptor.sensor or sensor_spec.sensor,
                "tile_id": chip.descriptor.tile_id,
                "scene_cloud_cover_pct": chip.descriptor.cloud_cover,
                "zone_total_pixels": in_zone,
                "zone_valid_pixels": valid_px_scene,
                "zone_masked_pixels": masked_px_scene,
                "zone_valid_fraction": float(valid_px_scene / in_zone) if in_zone else 0.0,
                "quality_usable_pixels": int(u_scene.sum()),
            }
            if sensor_spec.mask == "scl":
                uniq_vals, uniq_counts = np.unique(q_scene, return_counts=True)
                scl_counts = {
                    str(int(k)): int(v) for k, v in zip(uniq_vals, uniq_counts, strict=True)
                }
                cloud_shadow_px = int(np.isin(q_scene, (3, 8, 9, 10)).sum())
                nodata_px = int((q_scene == 0).sum())
                detail["scl_class_counts"] = scl_counts
                detail["cloud_and_shadow_pixels"] = cloud_shadow_px
                detail["nodata_pixels"] = nodata_px
            scene_masking_details.append(detail)

        zs = zonal_stats(pixel_medians[year_zone])
        zonal_summary = {
            "mean": _safe_float_or_none(zs.mean),
            "median": _safe_float_or_none(zs.median),
            "std": _safe_float_or_none(zs.std),
            "p10": _safe_float_or_none(zs.p10),
            "p90": _safe_float_or_none(zs.p90),
            "n_valid": zs.n_valid,
            "n_total": zs.n_total,
            "valid_fraction": zs.valid_fraction,
        }

        descriptors = [c.descriptor for c in chips]
        all_descriptors.extend(descriptors)
        scene_cc_tuple = tuple(d.cloud_cover for d in descriptors)
        finite_ccs = [c for c in scene_cc_tuple if c is not None and math.isfinite(c)]
        cc_mean = float(np.mean(finite_ccs)) if finite_ccs else None

        proc_meta: dict[str, Any] = {
            "chip_shape": [int(chip_shape[0]), int(chip_shape[1])],
            "mask_type": sensor_spec.mask,
            "invalid_classes_or_bits": (
                list(SCL_INVALID_CLASSES) if sensor_spec.mask == "scl" else "landsat_qa_pixel"
            ),
            "n_total_zone_pixels": in_zone,
            "n_valid_zone_pixels": n_valid_px,
            "n_masked_zone_pixels": n_masked_px,
            "zonal_stats": zonal_summary,
            "scene_masking": scene_masking_details,
        }

        records.append(
            AnnualObservationRecord(
                year=int(year),
                indicator=ind_name,
                value=value,
                n_valid_observations=n_valid_obs,
                clear_pixel_fraction=clear_frac,
                n_scenes=len(chips),
                scene_ids=tuple(d.id for d in descriptors),
                acquisition_dates=tuple(d.datetime for d in descriptors),
                sensor=sensor_spec.sensor,
                scenes_sha256=scenes_hash(descriptors),
                cloud_cover_mean=cc_mean,
                scene_cloud_cover=scene_cc_tuple,
                n_valid_pixels=n_valid_px,
                n_total_pixels=in_zone,
                n_masked_pixels=n_masked_px,
                indices=calculated_indices,
                processing_metadata=proc_meta,
            )
        )

    overall_sha256 = scenes_hash(all_descriptors)
    provenance = Provenance.computed(
        source=f"{sensor_spec.collection} ({data_origin.value})",
        method=f"aoi-zonal-median-mean/{ind_name}",
        stage="geospatial",
        parameters={
            "unit_id": unit_id,
            "indicator": ind_name,
            "sensor": sensor_spec.sensor,
            "bbox": list(bbox),
            "data_origin": data_origin.value,
            "catalog_url": catalog_url,
            "years": [r.year for r in records],
            "total_scenes": len(all_descriptors),
            "scene_ids": [d.id for d in all_descriptors],
            "acquisition_dates": [d.datetime for d in all_descriptors],
            "scenes_sha256": overall_sha256,
            "year_hashes": {str(r.year): r.scenes_sha256 for r in records},
            "year_indices": {
                str(r.year): {
                    k: _safe_float_or_none(v)
                    for k, v in (r.indices or {}).items()
                }
                for r in records
            },
            "year_valid_pixels": {str(r.year): r.n_valid_pixels for r in records},
            "year_total_pixels": {str(r.year): r.n_total_pixels for r in records},
            "year_masked_pixels": {str(r.year): r.n_masked_pixels for r in records},
        },
        notes=(
            "Per-scene spectral index masked by sensor quality layer, reduced via "
            "per-pixel annual median and zonal clear-pixel mean. Cloud-starved years "
            "remain NaN without interpolation."
        ),
    )
    if catalog_url is not None:
        provenance = provenance.model_copy(update={"source_uri": catalog_url})

    return AOIObservationBundle(
        unit_id=unit_id,
        indicator=ind_name,
        bbox=bbox,
        records=tuple(records),
        data_origin=data_origin,
        catalog_url=catalog_url,
        provenance=provenance,
    )


def fetch_aoi_chips_from_stac(
    aoi_geojson: dict[str, Any],
    years: Sequence[int],
    *,
    platform: str = "sentinel-2",
    max_cloud_cover: float = 25.0,
    date_window: tuple[str, str] = ("05-01", "09-30"),
    max_scenes_per_year: int = 4,
    tile_id: str | None = None,
    resolution_m: float = 100.0,
    catalog_url: str = DEFAULT_STAC_URL,
    client: Any | None = None,
    bands: Sequence[str] | None = None,
) -> tuple[dict[int, list[SceneRasterChip]], np.ndarray, RasterGridSpec, list[dict[str, Any]]]:
    """Search a live STAC catalog and retrieve windowed raster chips for an AOI across years.

    Never falls back to synthetic fixtures. Raises :class:`DataUnavailableError` or
    :class:`ConfigurationError` on network failures, missing assets, or empty STAC results.
    """
    if not years:
        raise ValueError("years must be a non-empty sequence of calendar years")
    if max_scenes_per_year < 1:
        raise ValueError("max_scenes_per_year must be >= 1")

    bbox = validate_aoi_geojson(aoi_geojson)
    geom_dict = _extract_geojson_geometry(aoi_geojson)

    if client is None:
        client = open_stac_client(catalog_url)

    if platform == "sentinel-2":
        target_bands = tuple(bands) if bands is not None else ("B02", "B04", "B08", "B11", "B12")
        quality_band = "SCL"
        radsat_band: str | None = None
    elif platform == "landsat":
        target_bands = (
            tuple(bands)
            if bands is not None
            else ("SR_B2", "SR_B4", "SR_B5", "SR_B6", "SR_B7")
        )
        quality_band = "QA_PIXEL"
        radsat_band = "QA_RADSAT"
    else:
        raise ValueError(f"Unsupported platform {platform!r}")

    start_mmdd, end_mmdd = date_window
    raw_scenes_by_year: dict[int, list[SceneDescriptor]] = {}
    tile_counts: dict[str, int] = {}

    for yr in sorted({int(y) for y in years}):
        found = search_scenes(
            bbox,
            f"{yr}-{start_mmdd}",
            f"{yr}-{end_mmdd}",
            platform=platform,
            max_cloud_cover=max_cloud_cover,
            catalog_url=catalog_url,
            limit=max(max_scenes_per_year * 6, 25),
            client=client,
            intersects=geom_dict,
            tile_id=tile_id,
            deduplicate_overpasses=True,
        )
        raw_scenes_by_year[yr] = found
        for s in found:
            if s.tile_id:
                tile_counts[s.tile_id] = tile_counts.get(s.tile_id, 0) + 1

    # Select dominant MGRS/WRS tile if not explicitly locked, so all chips share native UTM CRS
    chosen_tile = tile_id
    if chosen_tile is None and tile_counts:
        chosen_tile = max(sorted(tile_counts), key=lambda t: tile_counts[t])

    aoi_shape: Any = None
    try:
        import shapely.geometry as _shapely_geom

        aoi_shape = _shapely_geom.shape(geom_dict)
    except Exception:
        aoi_shape = None

    def _scene_overlap_area(scene: SceneDescriptor) -> float:
        if aoi_shape is None or not isinstance(scene.geometry, Mapping):
            return 1.0
        try:
            import shapely.geometry as _shapely_geom

            return float(aoi_shape.intersection(_shapely_geom.shape(scene.geometry)).area)
        except Exception:
            return 1.0

    selected_by_year: dict[int, list[SceneDescriptor]] = {}
    all_selected: list[SceneDescriptor] = []
    for yr, scenes in raw_scenes_by_year.items():
        filtered = (
            [s for s in scenes if s.tile_id == chosen_tile]
            if chosen_tile is not None
            else list(scenes)
        )
        overlaps = {s.id: _scene_overlap_area(s) for s in filtered}
        max_overlap = max(overlaps.values(), default=1.0) or 1.0
        filtered.sort(
            key=lambda s: (
                0 if (overlaps.get(s.id, 1.0) / max_overlap) >= 0.5 else 1,
                s.cloud_cover if s.cloud_cover is not None else 100.0,
                s.id,
            )
        )
        chosen = filtered[:max_scenes_per_year]
        selected_by_year[yr] = chosen
        all_selected.extend(chosen)

    if not all_selected:
        raise DataUnavailableError(
            f"Live STAC search on {catalog_url!r} returned 0 scenes for AOI bbox {bbox} "
            f"across years {sorted(raw_scenes_by_year)}. Refusing to substitute synthetic data."
        )

    grid, zone_mask = build_aoi_raster_grid(
        aoi_geojson,
        all_selected,
        resolution_m=resolution_m,
        quality_band=quality_band,
    )

    chips_by_year: dict[int, list[SceneRasterChip]] = {}
    fetch_metadata_list: list[dict[str, Any]] = []

    for yr in sorted(selected_by_year):
        yr_chips: list[SceneRasterChip] = []
        for scene in selected_by_year[yr]:
            bands_dn, quality_arr, radsat_arr, fetch_meta = fetch_scene_raster_data(
                scene,
                grid,
                bands=target_bands,
                quality_band=quality_band,
                radsat_band=radsat_band,
                harmonize_s2_baseline=True,
            )
            yr_chips.append(
                SceneRasterChip(
                    descriptor=scene,
                    bands_dn=bands_dn,
                    quality=quality_arr,
                    radsat=radsat_arr,
                )
            )
            fetch_metadata_list.append(fetch_meta)
        chips_by_year[yr] = yr_chips

    return chips_by_year, zone_mask, grid, fetch_metadata_list


def ingest_live_aoi_observations(
    unit_id: str,
    aoi_geojson: dict[str, Any],
    years: Sequence[int],
    *,
    indicators: Sequence[str | Indicator] = ("ndvi", "evi", "ndmi", "nbr"),
    platform: str = "sentinel-2",
    max_cloud_cover: float = 25.0,
    date_window: tuple[str, str] = ("05-01", "09-30"),
    max_scenes_per_year: int = 4,
    tile_id: str | None = None,
    resolution_m: float = 100.0,
    catalog_url: str = DEFAULT_STAC_URL,
    cache: AOIObservationCache | Path | str | None = None,
    client: Any | None = None,
) -> dict[str, AOIObservationBundle]:
    """End-to-end live satellite ingestion: STAC search, COG retrieval, masking, indices, cache.

    Connects to Microsoft Planetary Computer (or configured ``catalog_url``), retrieves
    real Sentinel-2 L2A / Landsat Collection 2 raster assets over ``aoi_geojson``,
    applies cloud/shadow masking, computes all requested vegetation indices (NDVI, EVI,
    NDMI, NBR), performs AOI-based zonal reduction, marks observations ``REAL_STAC``,
    and optionally persists them to :class:`AOIObservationCache`.
    """
    if not indicators:
        raise ValueError("indicators must be a non-empty sequence")
    resolved_inds = [_resolve_indicator(i) for i in indicators]

    chips_by_year, zone_mask, grid, fetch_meta = fetch_aoi_chips_from_stac(
        aoi_geojson,
        years,
        platform=platform,
        max_cloud_cover=max_cloud_cover,
        date_window=date_window,
        max_scenes_per_year=max_scenes_per_year,
        tile_id=tile_id,
        resolution_m=resolution_m,
        catalog_url=catalog_url,
        client=client,
    )

    cache_obj: AOIObservationCache | None = None
    if isinstance(cache, AOIObservationCache):
        cache_obj = cache
    elif isinstance(cache, (Path, str)):
        cache_obj = AOIObservationCache(cache)

    bundles: dict[str, AOIObservationBundle] = {}
    for ind_name in resolved_inds:
        bundle = reduce_aoi_scenes_to_series(
            unit_id=unit_id,
            aoi_geojson=aoi_geojson,
            chips_by_year=chips_by_year,
            indicator=ind_name,
            sensor=platform,
            zone_mask=zone_mask,
            data_origin=DataOrigin.REAL_STAC,
            catalog_url=catalog_url,
        )
        enriched_params = dict(bundle.provenance.parameters)
        enriched_params["raster_grid"] = {
            "crs": grid.crs,
            "utm_bounds": list(grid.bounds),
            "wgs84_intersection_bounds": list(grid.wgs84_bounds),
            "height": grid.height,
            "width": grid.width,
            "resolution_m": grid.resolution_m,
        }
        enriched_params["scenes_metadata"] = fetch_meta
        enriched_prov = bundle.provenance.model_copy(update={"parameters": enriched_params})
        bundle = AOIObservationBundle(
            unit_id=bundle.unit_id,
            indicator=bundle.indicator,
            bbox=bundle.bbox,
            records=bundle.records,
            data_origin=DataOrigin.REAL_STAC,
            catalog_url=bundle.catalog_url,
            provenance=enriched_prov,
        )
        if cache_obj is not None:
            cache_obj.put(bundle)
        bundles[ind_name] = bundle

    return bundles


_SAFE_KEY_RE = re.compile(r"^[A-Za-z0-9._-]+$")


class AOIObservationCache:
    """Disk-backed JSON cache for :class:`AOIObservationBundle` with strict origin enforcement.

    When a bundle with ``DataOrigin.REAL_STAC`` is loaded from disk, its origin
    transitions to ``DataOrigin.CACHED_REAL_STAC`` while preserving all original
    ``scene_ids``, ``acquisition_dates``, and ``scenes_sha256``.

    When ``require_real=True`` (the default), any attempt to retrieve a bundle
    marked ``DataOrigin.SYNTHETIC`` raises :class:`ValueError`.
    """

    def __init__(self, cache_dir: Path | str) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _validate_token(self, token: str, label: str) -> str:
        if not _SAFE_KEY_RE.match(token):
            raise ValueError(f"Unsafe {label} {token!r} for cache path")
        return token

    def cache_path(self, unit_id: str, indicator: str | Indicator) -> Path:
        """Return the deterministic JSON file path for ``(unit_id, indicator)``."""
        ind = indicator.value if isinstance(indicator, Indicator) else str(indicator).lower()
        safe_unit = self._validate_token(unit_id, "unit_id")
        safe_ind = self._validate_token(ind, "indicator")
        return self.cache_dir / f"{safe_unit}__{safe_ind}.json"

    def put(self, bundle: AOIObservationBundle) -> Path:
        """Persist an :class:`AOIObservationBundle` to disk as JSON."""
        path = self.cache_path(bundle.unit_id, bundle.indicator)
        payload = json.dumps(bundle.to_dict(), indent=2, sort_keys=True)
        path.write_text(payload, encoding="utf-8")
        return path

    save = put
    store = put

    def get(
        self,
        unit_id: str,
        indicator: str | Indicator,
        *,
        require_real: bool = True,
    ) -> AOIObservationBundle:
        """Load an :class:`AOIObservationBundle` from disk.

        Raises:
            FileNotFoundError: if no cached entry exists.
            ValueError: if ``require_real=True`` and the cached entry has
                ``data_origin == DataOrigin.SYNTHETIC``.
        """
        path = self.cache_path(unit_id, indicator)
        if not path.exists():
            raise FileNotFoundError(f"No cached observation bundle at {path}")
        raw = json.loads(path.read_text(encoding="utf-8"))
        stored_origin = DataOrigin(str(raw["data_origin"]))
        if require_real and stored_origin == DataOrigin.SYNTHETIC:
            raise ValueError(
                f"Refusing to serve SYNTHETIC cached bundle for unit {unit_id!r} "
                f"(indicator={indicator!r}) when require_real=True"
            )
        effective_origin = (
            DataOrigin.CACHED_REAL_STAC
            if stored_origin == DataOrigin.REAL_STAC
            else stored_origin
        )
        return AOIObservationBundle.from_dict(raw, override_origin=effective_origin)

    load = get


__all__ = [
    "AOIObservationBundle",
    "AOIObservationCache",
    "AnnualObservationRecord",
    "DataOrigin",
    "SceneRasterChip",
    "fetch_aoi_chips_from_stac",
    "ingest_live_aoi_observations",
    "reduce_aoi_scenes_to_series",
]
