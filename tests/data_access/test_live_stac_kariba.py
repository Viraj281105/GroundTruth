"""Live integration tests for Sentinel-2 L2A STAC discovery, COG retrieval, and AOI reduction.

These tests execute against the real Microsoft Planetary Computer STAC API and Azure Blob
Storage COG assets covering the Kariba REDD+ boundary (`cases/boundaries/kariba-redd.geojson`).
No mocks or synthetic fixtures are used here.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from groundtruth.contracts.ports import ObservationSpec
from groundtruth.contracts.request import UnitRef
from groundtruth.contracts.types import Indicator
from groundtruth.data_access.aoi_pipeline import (
    AOIObservationCache,
    DataOrigin,
    ingest_live_aoi_observations,
)
from groundtruth.data_access.stac import (
    DEFAULT_STAC_URL,
    open_stac_client,
    search_scenes,
    validate_aoi_geojson,
)
from groundtruth.platform.config import REPO_ROOT
from groundtruth.platform.datasets.access import (
    PLANETARY_COMPUTER_S2_DATASET,
    StacCachedObservationAccess,
)

KARIBA_BOUNDARY_PATH = REPO_ROOT / "cases" / "boundaries" / "kariba-redd.geojson"


def test_live_planetary_computer_kariba_sentinel2_ingestion_and_cache(tmp_path: Path) -> None:
    """Connect to live Microsoft Planetary Computer, ingest real Kariba Sentinel-2 scenes, and verify cache."""
    assert KARIBA_BOUNDARY_PATH.is_file(), f"Missing Kariba boundary at {KARIBA_BOUNDARY_PATH}"
    kariba_geojson = json.loads(KARIBA_BOUNDARY_PATH.read_text(encoding="utf-8"))
    bbox = validate_aoi_geojson(kariba_geojson)
    assert bbox == pytest.approx(
        (27.62576193948661, -17.71287498652449, 31.14510220919165, -15.62525449886945)
    )

    client = open_stac_client(DEFAULT_STAC_URL, sign_planetary_computer=True)

    # Verify live STAC search returns signed Sentinel-2 L2A items covering Kariba tile 36LTH
    scenes = search_scenes(
        bbox,
        "2023-06-01",
        "2023-06-30",
        platform="sentinel-2",
        max_cloud_cover=10.0,
        catalog_url=DEFAULT_STAC_URL,
        limit=10,
        client=client,
        tile_id="36LTH",
        deduplicate_overpasses=True,
    )
    assert len(scenes) >= 1
    first = scenes[0]
    assert first.collection == "sentinel-2-l2a"
    assert first.tile_id == "36LTH"
    for band in ("B02", "B04", "B08", "B11", "B12", "SCL"):
        assert band in first.asset_hrefs
        assert "sig=" in first.asset_hrefs[band]

    # Run end-to-end live raster retrieval, cloud masking, index computation, and caching
    cache = AOIObservationCache(tmp_path / "live_kariba_cache")
    bundles = ingest_live_aoi_observations(
        unit_id="kariba-redd",
        aoi_geojson=kariba_geojson,
        years=[2022, 2023],
        indicators=("ndvi", "evi", "ndmi", "nbr"),
        platform="sentinel-2",
        max_cloud_cover=15.0,
        date_window=("06-01", "06-30"),
        max_scenes_per_year=1,
        tile_id="36LTH",
        resolution_m=200.0,
        catalog_url=DEFAULT_STAC_URL,
        cache=cache,
        client=client,
    )

    assert set(bundles) == {"ndvi", "evi", "ndmi", "nbr"}

    for ind_name, bundle in bundles.items():
        # Live observation bundles must be marked REAL_STAC and never synthetic
        assert bundle.data_origin == DataOrigin.REAL_STAC
        assert not bundle.is_synthetic
        assert bundle.catalog_url == DEFAULT_STAC_URL
        assert len(bundle.records) == 2

        for rec in bundle.records:
            assert rec.year in (2022, 2023)
            assert rec.n_scenes == 1
            assert len(rec.scene_ids) == 1
            assert rec.scene_ids[0].startswith("S2")
            assert len(rec.acquisition_dates) == 1
            assert rec.sensor == "sentinel2"
            assert math.isfinite(rec.value)
            assert -1.0 <= rec.value <= 1.0
            assert rec.n_total_pixels is not None and rec.n_total_pixels > 50000
            assert rec.n_valid_pixels is not None and rec.n_valid_pixels > 50000
            assert rec.n_masked_pixels is not None and rec.n_masked_pixels >= 0
            assert rec.n_valid_pixels + rec.n_masked_pixels == rec.n_total_pixels
            assert 0.90 < rec.clear_pixel_fraction <= 1.0
            assert rec.indices is not None
            assert set(rec.indices) == {"ndvi", "evi", "ndmi", "nbr"}
            for idx_val in rec.indices.values():
                assert math.isfinite(idx_val)
                assert -1.0 <= idx_val <= 1.0

        # Reload from cache and verify transition to CACHED_REAL_STAC
        cached_bundle = cache.get("kariba-redd", ind_name, require_real=True)
        assert cached_bundle.data_origin == DataOrigin.CACHED_REAL_STAC
        assert not cached_bundle.is_synthetic
        assert cached_bundle.provenance.parameters["scenes_sha256"] == (
            bundle.provenance.parameters["scenes_sha256"]
        )
        assert cached_bundle.provenance.parameters["effective_data_origin"] == (
            DataOrigin.CACHED_REAL_STAC.value
        )
        assert [r.scene_ids for r in cached_bundle.records] == [
            r.scene_ids for r in bundle.records
        ]
        assert [r.value for r in cached_bundle.records] == pytest.approx(
            [r.value for r in bundle.records]
        )

    # Verify StacCachedObservationAccess serves the cached real STAC series
    obs_port = StacCachedObservationAccess(cache.cache_dir)
    assert obs_port.dataset(Indicator.NDVI) == PLANETARY_COMPUTER_S2_DATASET
    assert not obs_port.dataset(Indicator.NDVI).is_synthetic
    spec = ObservationSpec(
        unit=UnitRef(unit_id="kariba-redd"),
        indicator=Indicator.NDVI,
        start_period=2022,
        end_period=2023,
    )
    ts = obs_port.series(spec)
    assert ts.periods == (2022, 2023)
    assert all(0.20 < v < 0.65 for v in ts.values)

