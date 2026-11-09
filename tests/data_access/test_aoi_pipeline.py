"""Tests for the AOI-to-observation pipeline, NDMI index, GeoJSON validation, and cache."""

from __future__ import annotations

import math
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from groundtruth.data_access.aoi_pipeline import (
    AOIObservationCache,
    DataOrigin,
    SceneRasterChip,
    reduce_aoi_scenes_to_series,
)
from groundtruth.data_access.stac import (
    DEFAULT_STAC_URL,
    SceneDescriptor,
    scenes_hash,
    search_scenes,
    validate_aoi_geojson,
)
from groundtruth.engine.observation.indices import evi, nbr, ndmi, ndvi, savi

VALID_POLYGON_AOI: dict[str, Any] = {
    "type": "Polygon",
    "coordinates": [
        [
            [28.5, -16.8],
            [28.9, -16.8],
            [28.9, -16.4],
            [28.5, -16.4],
            [28.5, -16.8],
        ]
    ],
}

VALID_FEATURE_COLLECTION_AOI: dict[str, Any] = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {"name": "kariba-zone-a"},
            "geometry": VALID_POLYGON_AOI,
        }
    ],
}


def _make_descriptor(
    scene_id: str,
    dt: str,
    *,
    collection: str = "sentinel-2-l2a",
    sensor: str = "sentinel-2b",
    tile_id: str = "35LPM",
    cloud_cover: float = 10.0,
) -> SceneDescriptor:
    return SceneDescriptor(
        id=scene_id,
        collection=collection,
        datetime=dt,
        bbox=(28.5, -16.8, 28.9, -16.4),
        cloud_cover=cloud_cover,
        assets=("B04", "B08", "B11", "SCL"),
        href=f"https://planetarycomputer.microsoft.com/api/stac/v1/items/{scene_id}",
        sensor=sensor,
        tile_id=tile_id,
    )


def test_ndmi_calculation_and_bounds() -> None:
    nir = np.array([[0.50, 0.40, 0.0, 0.80]], dtype=float)
    swir1 = np.array([[0.25, 0.40, 0.0, 0.0]], dtype=float)
    result = ndmi(nir, swir1)

    assert result.shape == (1, 4)
    assert result[0, 0] == pytest.approx((0.50 - 0.25) / (0.50 + 0.25))
    assert result[0, 1] == pytest.approx(0.0)
    assert math.isnan(result[0, 2])
    assert result[0, 3] == pytest.approx(1.0)

    finite = result[~np.isnan(result)]
    assert np.all((finite >= -1.0) & (finite <= 1.0))

    # Existing spectral indices remain intact
    assert ndvi(np.array([0.6]), np.array([0.2]))[0] == pytest.approx(0.5)
    assert nbr(np.array([0.6]), np.array([0.2]))[0] == pytest.approx(0.5)
    assert savi(np.array([0.6]), np.array([0.2]))[0] == pytest.approx(0.46153846)
    assert evi(np.array([0.6]), np.array([0.2]), np.array([0.1]))[0] == pytest.approx(
        2.5 * (0.4 / (0.6 + 1.2 - 0.75 + 1.0))
    )


def test_validate_aoi_geojson_valid_geometries() -> None:
    bbox_poly = validate_aoi_geojson(VALID_POLYGON_AOI)
    assert bbox_poly == pytest.approx((28.5, -16.8, 28.9, -16.4))

    bbox_fc = validate_aoi_geojson(VALID_FEATURE_COLLECTION_AOI)
    assert bbox_fc == pytest.approx((28.5, -16.8, 28.9, -16.4))

    multi_poly: dict[str, Any] = {
        "type": "MultiPolygon",
        "coordinates": [VALID_POLYGON_AOI["coordinates"]],
    }
    assert validate_aoi_geojson(multi_poly) == pytest.approx((28.5, -16.8, 28.9, -16.4))


def test_validate_aoi_geojson_rejects_invalid_inputs() -> None:
    # Unclosed linear ring
    unclosed = {
        "type": "Polygon",
        "coordinates": [[[28.5, -16.8], [28.9, -16.8], [28.9, -16.4], [28.5, -16.4]]],
    }
    with pytest.raises(ValueError, match="not closed"):
        validate_aoi_geojson(unclosed)

    # Fewer than 4 positions
    too_short = {
        "type": "Polygon",
        "coordinates": [[[28.5, -16.8], [28.9, -16.8], [28.5, -16.8]]],
    }
    with pytest.raises(ValueError, match="at least 4 positions"):
        validate_aoi_geojson(too_short)

    # Out-of-range longitude (> 180)
    bad_lon = {
        "type": "Polygon",
        "coordinates": [
            [[185.0, -16.8], [186.0, -16.8], [186.0, -16.4], [185.0, -16.4], [185.0, -16.8]]
        ],
    }
    with pytest.raises(ValueError, match="Longitude"):
        validate_aoi_geojson(bad_lon)

    # Out-of-range latitude (< -90)
    bad_lat = {
        "type": "Polygon",
        "coordinates": [
            [[28.5, -95.0], [28.9, -95.0], [28.9, -16.4], [28.5, -16.4], [28.5, -95.0]]
        ],
    }
    with pytest.raises(ValueError, match="Latitude"):
        validate_aoi_geojson(bad_lat)

    # Degenerate zero-area bbox (horizontal line)
    zero_area = {
        "type": "Polygon",
        "coordinates": [[[28.5, -16.8], [28.9, -16.8], [28.7, -16.8], [28.5, -16.8]]],
    }
    with pytest.raises(ValueError, match="area"):
        validate_aoi_geojson(zero_area)


class _MockPlanetaryComputerClient:
    def __init__(self, items: list[Any]) -> None:
        self._items = items
        self.last_search_kwargs: dict[str, Any] = {}

    def search(self, **kwargs: Any) -> Any:
        self.last_search_kwargs = kwargs
        return SimpleNamespace(items=lambda: self._items)


def test_stac_search_sentinel2_and_landsat_descriptors() -> None:
    s2_item = SimpleNamespace(
        id="S2B_MSIL2A_20230615T075619_R035_T35LPM",
        collection_id="sentinel-2-l2a",
        properties={
            "datetime": "2023-06-15T07:56:19Z",
            "eo:cloud_cover": 8.4,
            "platform": "sentinel-2b",
            "s2:mgrs_tile": "35LPM",
        },
        bbox=[28.5, -16.8, 28.9, -16.4],
        assets={"B04": {}, "B08": {}, "B11": {}, "SCL": {}},
        get_self_href=lambda: "https://planetarycomputer.microsoft.com/api/stac/v1/s2_item",
    )
    s2_client = _MockPlanetaryComputerClient([s2_item])
    s2_scenes = search_scenes(
        (28.5, -16.8, 28.9, -16.4),
        "2023-01-01",
        "2023-12-31",
        platform="sentinel-2",
        max_cloud_cover=25.0,
        client=s2_client,
    )
    assert len(s2_scenes) == 1
    assert s2_scenes[0].collection == "sentinel-2-l2a"
    assert s2_scenes[0].sensor == "sentinel-2b"
    assert s2_scenes[0].tile_id == "35LPM"
    assert s2_client.last_search_kwargs["query"] == {"eo:cloud_cover": {"lt": 25.0}}

    ls_item = SimpleNamespace(
        id="LC08_L2SP_170072_20200710_02_T1",
        collection_id="landsat-c2-l2",
        properties={
            "datetime": "2020-07-10T08:11:00Z",
            "eo:cloud_cover": 3.2,
            "instruments": ["oli", "tirs"],
            "landsat:wrs_path": "170",
            "landsat:wrs_row": "072",
        },
        bbox=[28.5, -16.8, 28.9, -16.4],
        assets={"SR_B4": {}, "SR_B5": {}, "QA_PIXEL": {}},
        get_self_href=lambda: "https://planetarycomputer.microsoft.com/api/stac/v1/ls_item",
    )
    ls_client = _MockPlanetaryComputerClient([ls_item])
    ls_scenes = search_scenes(
        (28.5, -16.8, 28.9, -16.4),
        "2020-01-01",
        "2020-12-31",
        platform="landsat",
        client=ls_client,
    )
    assert len(ls_scenes) == 1
    assert ls_scenes[0].collection == "landsat-c2-l2"
    assert ls_scenes[0].sensor == "oli/tirs"
    assert ls_scenes[0].tile_id == "170/072"


def test_reduce_aoi_scenes_sentinel2_scl_masking_and_ndmi() -> None:
    # 2x2 chip in Sentinel-2 DN units (scale = 1e-4, offset = 0.0)
    # Scene 1: all 4 pixels clear (SCL = 4, vegetation)
    # NIR = 6000 (0.6), RED = 2000 (0.2) -> NDVI = (0.6 - 0.2) / 0.8 = 0.5
    # SWIR1 = 3000 (0.3) -> NDMI = (0.6 - 0.3) / 0.9 = 1/3
    desc_1 = _make_descriptor("S2_2022_01", "2022-05-10T08:00:00Z")
    chip_1 = SceneRasterChip(
        descriptor=desc_1,
        bands_dn={
            "B08": np.full((2, 2), 6000.0),
            "B04": np.full((2, 2), 2000.0),
            "B11": np.full((2, 2), 3000.0),
        },
        quality=np.full((2, 2), 4, dtype=int),
    )

    # Scene 2: top row is high-probability cloud (SCL = 9) with bogus bright values,
    # bottom row is clear (SCL = 4) with NIR = 7000 (0.7), RED = 1000 (0.1) -> NDVI = 0.75
    desc_2 = _make_descriptor("S2_2022_02", "2022-08-19T08:00:00Z")
    chip_2 = SceneRasterChip(
        descriptor=desc_2,
        bands_dn={
            "B08": np.array([[9500.0, 9500.0], [7000.0, 7000.0]]),
            "B04": np.array([[9000.0, 9000.0], [1000.0, 1000.0]]),
            "B11": np.array([[9000.0, 9000.0], [3500.0, 3500.0]]),
        },
        quality=np.array([[9, 3], [4, 4]], dtype=int),  # 9=cloud, 3=cloud shadow
    )

    desc_2023 = _make_descriptor("S2_2023_01", "2023-06-01T08:00:00Z")
    chip_2023 = SceneRasterChip(
        descriptor=desc_2023,
        bands_dn={
            "B08": np.full((2, 2), 5000.0),
            "B04": np.full((2, 2), 3000.0),
            "B11": np.full((2, 2), 2500.0),
        },
        quality=np.full((2, 2), 4, dtype=int),
    )

    bundle = reduce_aoi_scenes_to_series(
        unit_id="kariba-project",
        aoi_geojson=VALID_FEATURE_COLLECTION_AOI,
        chips_by_year={2022: [chip_1, chip_2], 2023: [chip_2023]},
        indicator="ndvi",
        sensor="sentinel-2",
    )

    assert not bundle.is_synthetic
    assert bundle.data_origin == DataOrigin.REAL_STAC
    assert len(bundle.records) == 2

    rec_2022 = bundle.records[0]
    # Top row median = 0.5 (1 clear scene); bottom row median = (0.5 + 0.75)/2 = 0.625 (2 clear scenes)
    # Zonal mean over all 4 clear pixels = (0.5 + 0.5 + 0.625 + 0.625) / 4 = 0.5625
    assert rec_2022.value == pytest.approx(0.5625)
    assert rec_2022.clear_pixel_fraction == pytest.approx(1.0)
    assert rec_2022.n_scenes == 2
    assert rec_2022.scene_ids == ("S2_2022_01", "S2_2022_02")
    assert rec_2022.scenes_sha256 == scenes_hash([desc_1, desc_2])

    # Also test NDMI reduction on the same chips
    ndmi_bundle = reduce_aoi_scenes_to_series(
        unit_id="kariba-project",
        aoi_geojson=VALID_POLYGON_AOI,
        chips_by_year={2022: [chip_1, chip_2], 2023: [chip_2023]},
        indicator="ndmi",
        sensor="sentinel2",
    )
    assert ndmi_bundle.records[0].value == pytest.approx(1.0 / 3.0)
    ts = ndmi_bundle.to_time_series()
    assert ts.periods == (2022, 2023)
    assert ts.unit == "ndmi"


def test_reduce_aoi_scenes_landsat_qa_pixel_and_radsat_masking() -> None:
    # Landsat Collection 2 scale = 0.0000275, offset = -0.2
    # For reflectance = 0.6 -> DN = (0.6 + 0.2) / 0.0000275 = 29090.90909
    # For reflectance = 0.2 -> DN = (0.2 + 0.2) / 0.0000275 = 14545.45455
    dn_06 = (0.6 + 0.2) / 0.0000275
    dn_02 = (0.2 + 0.2) / 0.0000275

    desc = _make_descriptor(
        "LC08_2021_01",
        "2021-07-15T08:00:00Z",
        collection="landsat-c2-l2",
        sensor="landsat-8",
        tile_id="170/072",
    )
    # Pixel (0, 0) clear (QA_PIXEL = 21824, low bits 0..5 all 0)
    # Pixel (0, 1) cloud bit 3 set (1 << 3 = 8)
    # Pixel (1, 0) radiometric saturation in QA_RADSAT
    # Pixel (1, 1) clear
    qa_pixel = np.array([[21824, 21824 | (1 << 3)], [21824, 21824]], dtype=int)
    radsat = np.array([[0, 0], [4, 0]], dtype=int)

    chip = SceneRasterChip(
        descriptor=desc,
        bands_dn={
            "SR_B5": np.array([[dn_06, 50000.0], [50000.0, dn_06]]),
            "SR_B4": np.array([[dn_02, 50000.0], [50000.0, dn_02]]),
        },
        quality=qa_pixel,
        radsat=radsat,
    )

    bundle = reduce_aoi_scenes_to_series(
        unit_id="landsat-unit",
        aoi_geojson=VALID_POLYGON_AOI,
        chips_by_year={2021: [chip]},
        indicator="ndvi",
        sensor="landsat8",
    )
    rec = bundle.records[0]
    assert rec.value == pytest.approx(0.5, rel=1e-5)
    assert rec.clear_pixel_fraction == pytest.approx(0.5)
    assert rec.sensor == "landsat8"


def test_100_percent_cloud_cover_and_empty_year_never_fabricate_data() -> None:
    desc_cloudy = _make_descriptor("S2_CLOUDY", "2021-01-10T08:00:00Z", cloud_cover=100.0)
    cloudy_chip = SceneRasterChip(
        descriptor=desc_cloudy,
        bands_dn={
            "nir": np.full((3, 3), 8000.0),
            "red": np.full((3, 3), 8000.0),
        },
        quality=np.full((3, 3), 9, dtype=int),  # 100% high-prob cloud
    )
    desc_clear = _make_descriptor("S2_CLEAR", "2022-06-10T08:00:00Z", cloud_cover=0.0)
    clear_chip = SceneRasterChip(
        descriptor=desc_clear,
        bands_dn={
            "nir": np.full((3, 3), 6000.0),
            "red": np.full((3, 3), 2000.0),
        },
        quality=np.full((3, 3), 4, dtype=int),
    )
    desc_clear_2 = _make_descriptor("S2_CLEAR_2", "2023-06-10T08:00:00Z", cloud_cover=0.0)
    clear_chip_2 = SceneRasterChip(
        descriptor=desc_clear_2,
        bands_dn={
            "nir": np.full((3, 3), 6000.0),
            "red": np.full((3, 3), 2000.0),
        },
        quality=np.full((3, 3), 4, dtype=int),
    )

    bundle = reduce_aoi_scenes_to_series(
        unit_id="cloud-starved-unit",
        aoi_geojson=VALID_POLYGON_AOI,
        chips_by_year={
            2020: [],  # 0 scenes
            2021: [cloudy_chip],  # 100% cloud cover
            2022: [clear_chip],
            2023: [clear_chip_2],
        },
        indicator="ndvi",
        sensor="sentinel2",
    )

    by_year = {r.year: r for r in bundle.records}
    assert math.isnan(by_year[2020].value)
    assert by_year[2020].n_valid_observations == 0
    assert by_year[2020].n_scenes == 0

    assert math.isnan(by_year[2021].value)
    assert by_year[2021].n_valid_observations == 0
    assert by_year[2021].clear_pixel_fraction == 0.0
    assert by_year[2021].n_scenes == 1

    assert by_year[2022].value == pytest.approx(0.5)
    assert by_year[2022].n_valid_observations == 1

    ts_all = bundle.to_time_series(drop_nan=False)
    assert ts_all.periods == (2020, 2021, 2022, 2023)
    assert math.isnan(ts_all.values[0]) and math.isnan(ts_all.values[1])
    assert ts_all.n_valid_observations == (0, 0, 1, 1)

    ts_clean = bundle.to_time_series(drop_nan=True)
    assert ts_clean.periods == (2022, 2023)
    assert ts_clean.values == pytest.approx((0.5, 0.5))


def test_aoi_observation_cache_roundtrip_and_synthetic_guard(tmp_path: Path) -> None:
    desc_1 = _make_descriptor("S2_2022", "2022-07-01T08:00:00Z")
    desc_2 = _make_descriptor("S2_2023", "2023-07-01T08:00:00Z")
    chips = {
        2022: [
            SceneRasterChip(
                descriptor=desc_1,
                bands_dn={"nir": np.full((2, 2), 6000.0), "red": np.full((2, 2), 2000.0)},
                quality=np.full((2, 2), 4, dtype=int),
            )
        ],
        2023: [
            SceneRasterChip(
                descriptor=desc_2,
                bands_dn={"nir": np.full((2, 2), 5000.0), "red": np.full((2, 2), 3000.0)},
                quality=np.full((2, 2), 4, dtype=int),
            )
        ],
    }

    real_bundle = reduce_aoi_scenes_to_series(
        unit_id="real-unit",
        aoi_geojson=VALID_POLYGON_AOI,
        chips_by_year=chips,
        indicator="ndvi",
        sensor="sentinel2",
        data_origin=DataOrigin.REAL_STAC,
        catalog_url=DEFAULT_STAC_URL,
    )

    cache = AOIObservationCache(tmp_path / "obs_cache")
    cache.put(real_bundle)

    loaded = cache.get("real-unit", "ndvi", require_real=True)
    assert loaded.data_origin == DataOrigin.CACHED_REAL_STAC
    assert not loaded.is_synthetic
    assert loaded.records[0].scenes_sha256 == real_bundle.records[0].scenes_sha256
    assert loaded.records[0].scene_ids == ("S2_2022",)
    assert loaded.records[0].value == pytest.approx(0.5)
    assert loaded.provenance.parameters["scenes_sha256"] == scenes_hash([desc_1, desc_2])

    # Now store a SYNTHETIC bundle and verify strict refusal when require_real=True
    synth_bundle = reduce_aoi_scenes_to_series(
        unit_id="synth-unit",
        aoi_geojson=VALID_POLYGON_AOI,
        chips_by_year=chips,
        indicator="ndvi",
        sensor="sentinel2",
        data_origin=DataOrigin.SYNTHETIC,
        catalog_url=None,
    )
    assert synth_bundle.is_synthetic
    cache.put(synth_bundle)

    with pytest.raises(ValueError, match="SYNTHETIC"):
        cache.get("synth-unit", "ndvi", require_real=True)

    allowed_synth = cache.get("synth-unit", "ndvi", require_real=False)
    assert allowed_synth.data_origin == DataOrigin.SYNTHETIC
    assert allowed_synth.is_synthetic


def test_multi_index_calculation_and_masking_metadata_in_reduction() -> None:
    desc = _make_descriptor("S2_MULTI_2023", "2023-06-30T07:46:21Z", cloud_cover=4.5)
    # 2x2 chip: 3 clear pixels (SCL=4,5), 1 cloud shadow pixel (SCL=3)
    chip = SceneRasterChip(
        descriptor=desc,
        bands_dn={
            "B02": np.array([[1000.0, 1000.0], [1000.0, 9000.0]]),
            "B04": np.array([[2000.0, 2000.0], [2000.0, 9000.0]]),
            "B08": np.array([[6000.0, 6000.0], [6000.0, 9000.0]]),
            "B11": np.array([[3000.0, 3000.0], [3000.0, 9000.0]]),
            "B12": np.array([[1500.0, 1500.0], [1500.0, 9000.0]]),
        },
        quality=np.array([[4, 5], [4, 3]], dtype=int),
    )
    bundle = reduce_aoi_scenes_to_series(
        unit_id="kariba-multi",
        aoi_geojson=VALID_POLYGON_AOI,
        chips_by_year={2023: [chip]},
        indicator="ndvi",
        sensor="sentinel2",
    )
    rec = bundle.records[0]
    assert rec.n_total_pixels == 4
    assert rec.n_valid_pixels == 3
    assert rec.n_masked_pixels == 1
    assert rec.clear_pixel_fraction == pytest.approx(0.75)
    assert rec.cloud_cover_mean == pytest.approx(4.5)
    assert rec.scene_cloud_cover == (4.5,)
    assert rec.indices is not None
    assert set(rec.indices) == {"ndvi", "evi", "ndmi", "nbr"}
    assert rec.indices["ndvi"] == pytest.approx((0.6 - 0.2) / (0.6 + 0.2))
    assert rec.indices["ndmi"] == pytest.approx((0.6 - 0.3) / (0.6 + 0.3))
    assert rec.indices["nbr"] == pytest.approx((0.6 - 0.15) / (0.6 + 0.15))
    assert rec.indices["evi"] == pytest.approx(2.5 * (0.6 - 0.2) / (0.6 + 1.2 - 0.75 + 1.0))
    assert rec.processing_metadata is not None
    scene_masking = rec.processing_metadata["scene_masking"][0]
    assert scene_masking["cloud_and_shadow_pixels"] == 1
    assert scene_masking["zone_valid_pixels"] == 3


def test_deduplicate_scene_overpasses_keeps_latest_baseline() -> None:
    from groundtruth.data_access.stac import deduplicate_scene_overpasses

    s_old = SceneDescriptor(
        id="S2A_MSIL2A_20230630T074621_R135_T36LTH_20230630T142624",
        collection="sentinel-2-l2a",
        datetime="2023-06-30T07:46:21.024000Z",
        bbox=(30.0, -17.0, 31.0, -16.0),
        cloud_cover=0.001,
        assets=("B04", "B08", "SCL"),
        tile_id="36LTH",
        processing_baseline="05.09",
    )
    s_new = SceneDescriptor(
        id="S2A_MSIL2A_20230630T074621_R135_T36LTH_20240911T231514",
        collection="sentinel-2-l2a",
        datetime="2023-06-30T07:46:21.024000Z",
        bbox=(30.0, -17.0, 31.0, -16.0),
        cloud_cover=0.001,
        assets=("B04", "B08", "SCL"),
        tile_id="36LTH",
        processing_baseline="05.10",
    )
    deduped = deduplicate_scene_overpasses([s_old, s_new])
    assert len(deduped) == 1
    assert deduped[0].id == s_new.id
    assert deduped[0].processing_baseline == "05.10"


def test_explicit_error_handling_for_network_credentials_and_missing_assets(
    tmp_path: Path,
) -> None:
    pytest.importorskip("rasterio", reason="needs the `geo` extra")
    from groundtruth.contracts.errors import ConfigurationError, DataUnavailableError
    from groundtruth.contracts.ports import ObservationSpec
    from groundtruth.contracts.request import UnitRef
    from groundtruth.contracts.types import Indicator
    from groundtruth.data_access.aoi_pipeline import fetch_aoi_chips_from_stac
    from groundtruth.data_access.stac import (
        RasterGridSpec,
        fetch_scene_raster_data,
        open_stac_client,
    )
    from groundtruth.platform.datasets.access import StacCachedObservationAccess

    # 1. Invalid STAC catalog URL raises ConfigurationError
    with pytest.raises(ConfigurationError, match="catalog_url"):
        open_stac_client("not-a-valid-url")

    # 2. Client raising 403 Forbidden raises ConfigurationError
    class _ForbiddenClient:
        def search(self, **_kwargs: Any) -> Any:
            raise RuntimeError("HTTP 403 Forbidden: invalid SAS token")

    with pytest.raises(ConfigurationError, match=r"invalid credentials|access denied"):
        search_scenes(
            (28.5, -16.8, 28.9, -16.4),
            "2023-01-01",
            "2023-12-31",
            client=_ForbiddenClient(),
        )

    # 3. Client raising network error raises DataUnavailableError
    class _BrokenNetworkClient:
        def search(self, **_kwargs: Any) -> Any:
            raise ConnectionError("Connection timed out reaching STAC API")

    with pytest.raises(DataUnavailableError, match="timed out"):
        search_scenes(
            (28.5, -16.8, 28.9, -16.4),
            "2023-01-01",
            "2023-12-31",
            client=_BrokenNetworkClient(),
        )

    # 4. Empty STAC search in fetch_aoi_chips_from_stac never falls back to synthetic data
    empty_client = _MockPlanetaryComputerClient([])
    with pytest.raises(DataUnavailableError, match="Refusing to substitute synthetic data"):
        fetch_aoi_chips_from_stac(
            VALID_POLYGON_AOI,
            [2023],
            client=empty_client,
        )

    # 5. Missing required band asset in fetch_scene_raster_data raises DataUnavailableError
    incomplete_scene = _make_descriptor("S2_MISSING_ASSET", "2023-06-30T07:46:21Z")
    grid = RasterGridSpec(
        crs="EPSG:32736",
        bounds=(200000.0, 8200000.0, 201000.0, 8201000.0),
        height=10,
        width=10,
        resolution_m=100.0,
        wgs84_bounds=(28.5, -16.8, 28.9, -16.4),
    )
    with pytest.raises(DataUnavailableError, match="missing required raster asset"):
        fetch_scene_raster_data(incomplete_scene, grid, bands=("B04", "B08"), quality_band="SCL")

    # 6. StacCachedObservationAccess serves CACHED_REAL_STAC and refuses SYNTHETIC
    cache = AOIObservationCache(tmp_path / "stac_port_cache")
    desc_22 = _make_descriptor("S2_2022", "2022-06-20T07:46:19Z")
    desc_23 = _make_descriptor("S2_2023", "2023-06-30T07:46:21Z")
    chips = {
        2022: [
            SceneRasterChip(
                descriptor=desc_22,
                bands_dn={"B08": np.full((2, 2), 6000.0), "B04": np.full((2, 2), 2000.0)},
                quality=np.full((2, 2), 4, dtype=int),
            )
        ],
        2023: [
            SceneRasterChip(
                descriptor=desc_23,
                bands_dn={"B08": np.full((2, 2), 6500.0), "B04": np.full((2, 2), 1800.0)},
                quality=np.full((2, 2), 4, dtype=int),
            )
        ],
    }
    real_bundle = reduce_aoi_scenes_to_series(
        unit_id="kariba-redd",
        aoi_geojson=VALID_POLYGON_AOI,
        chips_by_year=chips,
        indicator="ndvi",
        sensor="sentinel2",
        data_origin=DataOrigin.REAL_STAC,
    )
    cache.put(real_bundle)

    port = StacCachedObservationAccess(cache.cache_dir)
    assert not port.dataset(Indicator.NDVI).is_synthetic
    spec = ObservationSpec(
        unit=UnitRef(unit_id="kariba-redd"),
        indicator=Indicator.NDVI,
        start_period=2022,
        end_period=2023,
    )
    ts = port.series(spec)
    assert ts.periods == (2022, 2023)
    prov = port.provenance(spec)
    assert prov.parameters["effective_data_origin"] == DataOrigin.CACHED_REAL_STAC.value

    synth_bundle = reduce_aoi_scenes_to_series(
        unit_id="synth-only",
        aoi_geojson=VALID_POLYGON_AOI,
        chips_by_year=chips,
        indicator="ndvi",
        sensor="sentinel2",
        data_origin=DataOrigin.SYNTHETIC,
    )
    cache.put(synth_bundle)
    with pytest.raises(DataUnavailableError, match="SYNTHETIC"):
        port.series(
            ObservationSpec(
                unit=UnitRef(unit_id="synth-only"),
                indicator=Indicator.NDVI,
                start_period=2022,
                end_period=2023,
            )
        )
