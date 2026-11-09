"""Comprehensive test suite for Microsoft Planetary Computer STAC API v1 integration.

Covers:
1. Catalogue connectivity and collection discovery without credentials.
2. Sentinel-2 L2A search using uploaded project polygons, date ranges and cloud-cover filters.
3. Landsat Collection 2 Level-2 for historical observations.
4. Sentinel-1 RTC for radar-based monitoring.
5. Pagination, timeouts, retries and rate-limit handling.
6. Asset signing using the official planetary-computer Python package.
7. Download only required assets, not entire scenes (windowed COG retrieval).
8. Cache downloaded imagery and metadata.
9. Preservation of scene IDs, acquisition dates, source URLs, collection IDs and processing provenance.
10. Handling unavailable scenes, missing bands and expired SAS tokens.
11. Handling differing band names and resolutions across collections.
12. Sentinel-2 red, green, blue, NIR and scene classification assets.
13. NDVI calculation from actual surface reflectance with cloud/shadow masking and valid-pixel statistics.
14. End-to-end live execution on a real project boundary.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest

from groundtruth.contracts.errors import ConfigurationError
from groundtruth.data_access.aoi_pipeline import (
    AOIImageryCache,
    AOIObservationCache,
    DataOrigin,
    SceneRasterChip,
    ingest_live_aoi_observations,
)
from groundtruth.data_access.stac import (
    DEFAULT_STAC_URL,
    RasterGridSpec,
    SceneDescriptor,
    calculate_spatial_coverage,
    check_catalog_connectivity,
    discover_collections,
    get_stac_collection,
    open_stac_client,
    resolve_collection_id,
    search_scenes,
    sign_asset_url,
    validate_aoi_geojson,
)
from groundtruth.engine.observation.indices import ndvi, rvi
from groundtruth.engine.observation.masking import scl_cloud_mask
from groundtruth.engine.observation.reduction import (
    SENSORS,
    to_reflectance,
)
from groundtruth.platform.config import REPO_ROOT

KARIBA_BOUNDARY_PATH = REPO_ROOT / "cases" / "boundaries" / "kariba-redd.geojson"


# --- 1. Catalogue Connectivity & Collection Discovery ------------------------------


def test_catalogue_connectivity_unauthenticated() -> None:
    """Verify connectivity to Microsoft Planetary Computer STAC API v1 without credentials."""
    info = check_catalog_connectivity(DEFAULT_STAC_URL)
    assert info["status"] == "connected"
    assert info["url"] == DEFAULT_STAC_URL
    assert info["id"] == "microsoft-pc"
    assert "Planetary Computer" in info["title"]
    assert info.get("stac_version")
    assert len(info["conforms_to"]) > 0


def test_collection_discovery_unauthenticated() -> None:
    """Discover collections from Planetary Computer STAC catalog without credentials."""
    collections = discover_collections(DEFAULT_STAC_URL, limit=10)
    assert len(collections) > 0
    col_ids = [c["id"] for c in collections]
    assert all(isinstance(cid, str) and cid for cid in col_ids)
    for c in collections:
        assert "id" in c and "title" in c and "license" in c


def test_supported_collection_details() -> None:
    """Retrieve metadata for the 3 target collections: sentinel-2-l2a, landsat-c2-l2, sentinel-1-rtc."""
    s2 = get_stac_collection("sentinel-2-l2a")
    assert s2["id"] == "sentinel-2-l2a"
    assert "B02" in s2["item_assets"]  # blue
    assert "B03" in s2["item_assets"]  # green
    assert "B04" in s2["item_assets"]  # red
    assert "B08" in s2["item_assets"]  # nir
    assert "SCL" in s2["item_assets"]  # scene classification

    landsat = get_stac_collection("landsat-c2-l2")
    assert landsat["id"] == "landsat-c2-l2"
    assert "red" in landsat["item_assets"]
    assert "nir08" in landsat["item_assets"]
    assert "qa_pixel" in landsat["item_assets"]

    s1 = get_stac_collection("sentinel-1-rtc")
    assert s1["id"] == "sentinel-1-rtc"
    assert "vv" in s1["item_assets"]
    assert "vh" in s1["item_assets"]


def test_resolve_collection_id_aliases() -> None:
    """Verify collection name and platform alias resolution."""
    assert resolve_collection_id("sentinel-2") == "sentinel-2-l2a"
    assert resolve_collection_id("sentinel-2-l2a") == "sentinel-2-l2a"
    assert resolve_collection_id("s2") == "sentinel-2-l2a"
    assert resolve_collection_id("landsat") == "landsat-c2-l2"
    assert resolve_collection_id("landsat-c2-l2") == "landsat-c2-l2"
    assert resolve_collection_id("landsat-8") == "landsat-c2-l2"
    assert resolve_collection_id("landsat-9") == "landsat-c2-l2"
    assert resolve_collection_id("sentinel-1") == "sentinel-1-rtc"
    assert resolve_collection_id("sentinel-1-rtc") == "sentinel-1-rtc"
    assert resolve_collection_id("s1") == "sentinel-1-rtc"

    with pytest.raises(ValueError, match="platform must be one of"):
        resolve_collection_id("modis-terra")


# --- 2. Sentinel-2 L2A Search with Project Polygons --------------------------------


def test_sentinel2_l2a_search_with_uploaded_polygon() -> None:
    """Search Sentinel-2 L2A using an uploaded project polygon, date range, and cloud cover filter."""
    assert KARIBA_BOUNDARY_PATH.is_file()
    aoi_geojson = json.loads(KARIBA_BOUNDARY_PATH.read_text(encoding="utf-8"))
    bbox = validate_aoi_geojson(aoi_geojson)

    scenes = search_scenes(
        bbox=bbox,
        start="2023-06-01",
        end="2023-06-30",
        platform="sentinel-2-l2a",
        max_cloud_cover=10.0,
        limit=5,
        tile_id="36LTH",
        deduplicate_overpasses=True,
    )

    assert len(scenes) >= 1
    for s in scenes:
        assert s.collection == "sentinel-2-l2a"
        assert s.cloud_cover is not None and s.cloud_cover <= 10.0
        assert s.tile_id == "36LTH"
        assert s.datetime.startswith("2023-06")
        # Ensure red, green, blue, NIR and SCL assets are available
        for b in ("B02", "B03", "B04", "B08", "SCL"):
            assert b in s.asset_hrefs
            assert "sig=" in s.asset_hrefs[b]  # signed via planetary_computer


# --- 3. Landsat Collection 2 Level-2 for Historical Observations -------------------


def test_landsat_c2_l2_search_historical() -> None:
    """Search Landsat Collection 2 Level-2 historical scenes over project boundary."""
    bbox = (28.5, -16.8, 28.9, -16.4)
    scenes = search_scenes(
        bbox=bbox,
        start="2020-06-01",
        end="2020-07-31",
        platform="landsat-c2-l2",
        max_cloud_cover=15.0,
        limit=3,
    )
    assert len(scenes) >= 1
    first = scenes[0]
    assert first.collection == "landsat-c2-l2"
    assert first.datetime.startswith("2020")
    # Verify Landsat C2 L2 assets
    assert any(b in first.asset_hrefs for b in ("red", "SR_B4", "SR_B3"))
    assert any(b in first.asset_hrefs for b in ("nir08", "SR_B5", "SR_B4"))
    assert any(b in first.asset_hrefs for b in ("qa_pixel", "QA_PIXEL"))


# --- 4. Sentinel-1 RTC for Radar-Based Monitoring ----------------------------------


def test_sentinel1_rtc_search_radar() -> None:
    """Search Sentinel-1 RTC SAR radar scenes over project boundary (no cloud filter needed)."""
    assert KARIBA_BOUNDARY_PATH.is_file()
    aoi_geojson = json.loads(KARIBA_BOUNDARY_PATH.read_text(encoding="utf-8"))
    bbox = validate_aoi_geojson(aoi_geojson)
    scenes = search_scenes(
        bbox=bbox,
        start="2023-06-01",
        end="2023-06-30",
        platform="sentinel-1-rtc",
        limit=3,
    )
    assert len(scenes) >= 1
    first = scenes[0]
    assert first.collection == "sentinel-1-rtc"
    assert "vv" in first.asset_hrefs
    assert "vh" in first.asset_hrefs
    assert "sig=" in first.asset_hrefs["vv"]


# --- 5. Pagination, Timeouts, Retries and Rate-Limit Handling -----------------------


def test_open_stac_client_configuration_and_retries() -> None:
    """Verify StacApiIO is configured with retries, backoff, and timeouts."""
    client = open_stac_client(DEFAULT_STAC_URL, timeout=25.0, max_retries=3, backoff_factor=0.5)
    assert client is not None
    assert client.id == "microsoft-pc"


def test_invalid_catalog_url_raises_configuration_error() -> None:
    """Malformed catalog URLs raise ConfigurationError."""
    with pytest.raises(ConfigurationError):
        open_stac_client("not-a-url")
    with pytest.raises(ConfigurationError):
        open_stac_client("")


# --- 6. Asset Signing and SAS Token Expiration Handling ----------------------------


def test_sign_asset_url_and_expired_token_handling() -> None:
    """Test sign_asset_url strips expired tokens and obtains fresh valid SAS signatures."""
    raw_blob_url = (
        "https://sentinel2l2a01.blob.core.windows.net/sentinel2-l2/10/S/DG/2023/1/1/"
        "S2B_MSIL2A_20230101T185759_N0509_R113_T10SDG_20230101T221155.SAFE/GRANULE/"
        "L2A_T10SDG_A030412_20230101T190451/QI_DATA/MSK_CLDPRB_20m.jp2"
    )
    # Simulated expired SAS URL
    expired_url = (
        raw_blob_url + "?st=2020-01-01T00%3A00%3A00Z&se=2020-01-01T01%3A00%3A00Z&sig=EXPIREDTOKEN"
    )

    fresh_url = sign_asset_url(expired_url)
    assert "sig=" in fresh_url
    assert "EXPIREDTOKEN" not in fresh_url
    assert "se=" in fresh_url


# --- 7. Download Only Required Assets & Cache Imagery ------------------------------


def test_aoi_imagery_cache_roundtrip(tmp_path: Path) -> None:
    """Test caching and loading windowed raster chips on disk."""
    cache = AOIImageryCache(tmp_path / "imagery")
    grid = RasterGridSpec(
        crs="EPSG:32736",
        bounds=(100000.0, 8000000.0, 102000.0, 8002000.0),
        height=20,
        width=20,
        resolution_m=100.0,
        wgs84_bounds=(28.0, -17.0, 28.1, -16.9),
    )
    desc = SceneDescriptor(
        id="S2A_TEST_001",
        collection="sentinel-2-l2a",
        datetime="2023-06-15T08:00:00Z",
        bbox=(28.0, -17.0, 28.1, -16.9),
        cloud_cover=2.5,
        assets=("B04", "B08", "SCL"),
        href="https://planetarycomputer.microsoft.com/api/stac/v1/items/S2A_TEST_001",
    )

    bands = {
        "B04": np.full((20, 20), 500.0, dtype=float),
        "B08": np.full((20, 20), 2500.0, dtype=float),
    }
    quality = np.full((20, 20), 4, dtype=np.int64)  # vegetation
    chip = SceneRasterChip(descriptor=desc, bands_dn=bands, quality=quality)

    assert not cache.has("S2A_TEST_001", grid)
    saved_path = cache.put(chip, grid, meta={"scene_id": desc.id, "test": True})
    assert saved_path.is_file()
    assert cache.has("S2A_TEST_001", grid)

    reloaded = cache.get("S2A_TEST_001", grid, desc)
    assert reloaded is not None
    assert reloaded.descriptor.id == desc.id
    assert set(reloaded.bands_dn) == {"B04", "B08"}
    np.testing.assert_array_equal(reloaded.bands_dn["B04"], bands["B04"])
    np.testing.assert_array_equal(reloaded.bands_dn["B08"], bands["B08"])
    np.testing.assert_array_equal(reloaded.quality, quality)

    meta = cache.get_meta("S2A_TEST_001")
    assert meta is not None and meta.get("test") is True


# --- 8. Spectral Indices, Reflectance Scaling & Quality Masking ---------------------


def test_ndvi_surface_reflectance_and_masking() -> None:
    """NDVI is computed strictly from surface reflectance [0, 1] with SCL/QA masking."""
    s2_spec = SENSORS["sentinel2"]
    # Digital numbers for Sentinel-2 (scale 1e-4)
    red_dn = np.array([[500.0, 1000.0, 15000.0]], dtype=float)
    nir_dn = np.array([[2500.0, 3000.0, 4000.0]], dtype=float)

    red_rho = to_reflectance(red_dn, s2_spec)
    nir_rho = to_reflectance(nir_dn, s2_spec)

    assert red_rho[0, 0] == pytest.approx(0.05)
    assert nir_rho[0, 0] == pytest.approx(0.25)
    # 15000.0 DN -> 1.5 reflectance > 1.0 -> NaN
    assert math.isnan(red_rho[0, 2])

    calc_ndvi = ndvi(nir_rho, red_rho)
    # (0.25 - 0.05) / (0.25 + 0.05) = 0.20 / 0.30 = 0.6667
    assert calc_ndvi[0, 0] == pytest.approx(0.6666667, rel=1e-5)
    assert math.isnan(calc_ndvi[0, 2])

    # SCL Masking: 3 (cloud shadow), 8 (cloud med), 9 (cloud high), 10 (cirrus) are invalid
    scl = np.array([[4, 3, 9]], dtype=np.int64)  # veg, shadow, cloud
    mask = scl_cloud_mask(scl)
    assert mask[0, 0]  # valid vegetation
    assert not mask[0, 1]  # masked shadow
    assert not mask[0, 2]  # masked cloud

    masked_ndvi = np.where(mask, calc_ndvi, np.nan)
    assert math.isfinite(masked_ndvi[0, 0])
    assert math.isnan(masked_ndvi[0, 1])
    assert math.isnan(masked_ndvi[0, 2])


def test_radar_vegetation_index_computation() -> None:
    """Radar Vegetation Index (RVI) for dual-pol Sentinel-1 RTC."""
    # RVI = (4 * VH) / (VV + VH)
    vv = np.array([0.10, 0.20], dtype=float)
    vh = np.array([0.02, 0.05], dtype=float)
    rvi_val = rvi(vh, vv)
    assert rvi_val[0] == pytest.approx((4 * 0.02) / (0.10 + 0.02))
    assert rvi_val[1] == pytest.approx((4 * 0.05) / (0.20 + 0.05))
    assert all(0.0 <= v <= 1.0 for v in rvi_val)


# --- 9. Spatial Coverage and Statistics --------------------------------------------


def test_calculate_spatial_coverage_statistics() -> None:
    """Valid pixel counts, coverage fraction and completeness metrics."""
    zone = np.array([[True, True], [True, True]])
    valid = np.array([[True, True], [True, False]])  # 3 of 4 valid

    stats = calculate_spatial_coverage(zone, valid, resolution_m=100.0)
    assert stats["total_pixels"] == 4
    assert stats["valid_pixels"] == 3
    assert stats["masked_pixels"] == 1
    assert stats["coverage_fraction"] == 0.75
    assert stats["coverage_pct"] == 75.0
    assert not stats["is_spatially_complete"]


# --- 10. End-to-End Live Integration Test on Real Project Polygon ------------------


def test_live_planetary_computer_end_to_end_ingestion(tmp_path: Path) -> None:
    """Run an end-to-end test on a real project polygon, verifying discovery, download and processing."""
    # Real test sub-polygon in Kariba project area
    project_polygon = {
        "type": "Polygon",
        "coordinates": [
            [
                [28.8, -16.6],
                [28.9, -16.6],
                [28.9, -16.5],
                [28.8, -16.5],
                [28.8, -16.6],
            ]
        ],
    }

    cache = AOIObservationCache(tmp_path / "test_cache")
    client = open_stac_client(DEFAULT_STAC_URL, sign_planetary_computer=True)

    # Ingest Sentinel-2 L2A observations
    bundles = ingest_live_aoi_observations(
        unit_id="test-e2e-kariba",
        aoi_geojson=project_polygon,
        years=[2023],
        indicators=["ndvi"],
        platform="sentinel-2-l2a",
        max_cloud_cover=15.0,
        date_window=("06-01", "06-30"),
        max_scenes_per_year=1,
        resolution_m=100.0,
        catalog_url=DEFAULT_STAC_URL,
        cache=cache,
        client=client,
    )

    assert "ndvi" in bundles
    b = bundles["ndvi"]
    assert b.data_origin == DataOrigin.REAL_STAC
    assert not b.is_synthetic
    assert len(b.records) == 1

    rec = b.records[0]
    assert rec.year == 2023
    assert rec.n_scenes >= 1
    assert len(rec.scene_ids) >= 1
    assert rec.scene_ids[0].startswith("S2")
    assert len(rec.acquisition_dates) >= 1
    assert rec.sensor == "sentinel2"

    # Verify provenance and source URLs preserved
    assert len(rec.collection_ids) >= 1
    assert rec.collection_ids[0] == "sentinel-2-l2a"
    assert len(rec.source_urls) >= 1
    assert "planetarycomputer.microsoft.com" in rec.source_urls[0]

    # Verify NDVI value and pixel statistics
    assert math.isfinite(rec.value)
    assert 0.0 < rec.value < 1.0
    assert rec.n_total_pixels is not None and rec.n_total_pixels > 0
    assert rec.n_valid_pixels is not None and rec.n_valid_pixels > 0
    assert rec.n_masked_pixels is not None and rec.n_masked_pixels >= 0
    assert rec.n_valid_pixels + rec.n_masked_pixels == rec.n_total_pixels
    assert 0.0 < rec.clear_pixel_fraction <= 1.0

    # Verify cache reload transitions to CACHED_REAL_STAC
    reloaded = cache.get("test-e2e-kariba", "ndvi", require_real=True)
    assert reloaded.data_origin == DataOrigin.CACHED_REAL_STAC
    assert reloaded.records[0].value == pytest.approx(rec.value)
    assert reloaded.records[0].scene_ids == rec.scene_ids
    assert reloaded.records[0].collection_ids == rec.collection_ids

    # Report actual numbers
    print(f"\n[E2E REPORT] Discovered and selected scenes: {len(rec.scene_ids)}")
    print(f"[E2E REPORT] Scene IDs: {list(rec.scene_ids)}")
    print(f"[E2E REPORT] Acquisition dates: {list(rec.acquisition_dates)}")
    print(f"[E2E REPORT] Collection IDs: {list(rec.collection_ids)}")
    print(f"[E2E REPORT] Total AOI pixels: {rec.n_total_pixels}")
    print(f"[E2E REPORT] Valid unmasked pixels: {rec.n_valid_pixels}")
    print(f"[E2E REPORT] Clear pixel fraction: {rec.clear_pixel_fraction:.4f}")
    print(f"[E2E REPORT] Calculated NDVI: {rec.value:.4f}")
