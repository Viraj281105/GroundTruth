"""The Earth Engine observation service against the real Earth Engine (#22).

**Opt-in.** Skipped unless ``--run-network`` is passed, so it never runs in CI:

    pytest -m network --run-network tests/test_earthengine_network.py -v -s

It needs ``earthengine-api`` (``pip install -e "packages/groundtruth[earthengine]"``),
``GEE_SERVICE_ACCOUNT_JSON`` (a key file path or the key JSON) and, unless the
key names one, ``GOOGLE_CLOUD_PROJECT``. With ``--run-network`` and anything
missing, the tests fail with the reason — they do not skip, because a run you
asked for should not quietly do nothing.

Two checks:

1. **The acceptance criterion:** a real NDVI series for the Kariba registry
   boundary, 2001-2022 on Landsat 7 (agreed with Viraj, C3), with
   ``n_valid_observations`` for every year, pinned, then served again from the
   cache without contacting Earth Engine.
2. **The translation is faithful:** on a small chip inside the boundary, the
   Earth Engine reduction agrees with the engine's numpy reference
   ``reduce_period`` applied to the same pixels.
"""

from __future__ import annotations

import math
import pathlib
from typing import Any

import numpy as np
import pytest

from groundtruth.contracts.ports import ObservationSpec
from groundtruth.contracts.request import UnitRef
from groundtruth.contracts.types import Indicator
from groundtruth.engine.observation.reduction import reduce_period, reduction_spec
from groundtruth.platform.config import get_settings, reset_settings_cache
from groundtruth.platform.datasets.cache import ReductionCache
from groundtruth.platform.datasets.catalog import SNAPSHOT_DATE, SNAPSHOT_MICROS
from groundtruth.platform.datasets.earthengine import (
    CRS,
    EarthEngineApiBackend,
    ServiceAccountKey,
    YearQuery,
    import_ee,
)
from groundtruth.platform.datasets.observation import EarthEngineObservationAccess
from groundtruth.platform.datasets.resilience import RateLimiter
from groundtruth.platform.units.boundary import load_registry_boundary

pytestmark = pytest.mark.network

REPO = pathlib.Path(__file__).resolve().parents[1]
KARIBA_BOUNDARY = REPO / "cases" / "boundaries" / "kariba-redd.geojson"

# 0.01 degree square inside part 4 of the Kariba boundary (all corners checked).
CHIP = {
    "type": "Polygon",
    "coordinates": [
        [[30.60, -16.20], [30.61, -16.20], [30.61, -16.19], [30.60, -16.19], [30.60, -16.20]]
    ],
}


class CountingBackend(EarthEngineApiBackend):
    """The real backend, counting the calls that reach Earth Engine."""

    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    def list_scenes(self, query: YearQuery) -> dict[str, Any]:
        self.calls += 1
        return super().list_scenes(query)

    def reduce(self, query: YearQuery) -> dict[str, Any]:
        self.calls += 1
        return super().reduce(query)


class UnreachableBackend:
    """Fails the test if anything tries to contact Earth Engine."""

    def initialize(self, key: ServiceAccountKey, project: str) -> None:
        raise AssertionError("a cache hit must not sign in")

    def list_scenes(self, query: YearQuery) -> dict[str, Any]:
        raise AssertionError("a cache hit must not list scenes")

    def reduce(self, query: YearQuery) -> dict[str, Any]:
        raise AssertionError("a cache hit must not reduce")


def real_service(cache_dir: pathlib.Path, backend: Any) -> EarthEngineObservationAccess:
    reset_settings_cache()
    settings = get_settings()
    return EarthEngineObservationAccess(
        sensor="landsat7",
        credentials=settings.gee_service_account_json,
        project=settings.google_cloud_project,
        cache=ReductionCache(cache_dir),
        backend=backend,
        rate_limiter=RateLimiter(settings.earth_engine_max_requests_per_minute),
    )


def test_a_real_kariba_ndvi_series_is_pinned_and_observation_counted(tmp_path):
    boundary = load_registry_boundary(KARIBA_BOUNDARY)
    spec = ObservationSpec(
        unit=boundary.as_unit_ref(), indicator=Indicator.NDVI, start_period=2001, end_period=2022
    )
    backend = CountingBackend()
    service = real_service(tmp_path, backend)

    series = service.series(spec)
    provenance = service.provenance(spec)

    print(
        f"\nKariba NDVI, Landsat 7, snapshot {SNAPSHOT_DATE}, boundary sha256 "
        f"{boundary.content_sha256[:16]}..., geometry {provenance.parameters['geometry_blake2b']}"
    )
    print(f"{'year':>4} {'ndvi':>8} {'n_valid':>7} {'clear':>6} {'scenes':>6}")
    years = provenance.parameters["years"]
    for period, value, n in zip(
        series.periods, series.values, series.n_valid_observations or (), strict=True
    ):
        y = years[str(period)]
        print(
            f"{period:>4} {value:>8.4f} {n:>7} {y['clear_pixel_fraction']:>6.3f} {y['n_scenes']:>6}"
        )

    assert series.periods == tuple(range(2001, 2023))
    assert series.n_valid_observations is not None
    assert len(series.n_valid_observations) == 22
    assert all(isinstance(n, int) and n >= 0 for n in series.n_valid_observations)
    for value, n in zip(series.values, series.n_valid_observations, strict=True):
        if math.isnan(value):
            assert n == 0, "a NaN year must be one with no clear observation"
        else:
            assert -1.0 <= value <= 1.0

    ref = service.dataset(Indicator.NDVI)
    assert ref.version == f"C02-T1-L2@{SNAPSHOT_DATE}"
    assert not ref.is_synthetic
    assert provenance.parameters["dataset"] == str(ref)
    assert set(years) == {str(p) for p in series.periods}
    assert all(y["scene_fingerprint"] and not y["cache_hit"] for y in years.values())
    assert backend.calls >= 22

    again = real_service(tmp_path, UnreachableBackend()).series(spec)
    assert again.n_valid_observations == series.n_valid_observations
    assert again.values == pytest.approx(series.values, nan_ok=True)


def test_the_earth_engine_reduction_matches_the_engine_reference_on_a_chip(tmp_path):
    service = real_service(tmp_path, EarthEngineApiBackend())
    spec = ObservationSpec(
        unit=UnitRef(unit_id="kariba-chip", geometry=CHIP),
        indicator=Indicator.NDVI,
        start_period=2009,
        end_period=2010,
    )
    observed = service.series(spec)  # also signs this process in to Earth Engine

    ee = import_ee()
    reference_spec = reduction_spec(Indicator.NDVI, "landsat7")
    bands = reference_spec.sensor.bands
    names = [bands["nir"], bands["red"], "QA_PIXEL", "QA_RADSAT"]
    region = ee.Geometry(CHIP, None, True, False)

    for i, year in enumerate(observed.periods):
        start = ee.Date.fromYMD(year, 1, 1)
        scenes = (
            ee.ImageCollection(reference_spec.sensor.collection)
            .filterBounds(region)
            .filterDate(start, start.advance(1, "year"))
            .filter(ee.Filter.lte("system:version", SNAPSHOT_MICROS))
        )
        # The same grid the service reduces on, sampled pixel by pixel. Masked
        # pixels come back as 0, which the reference turns into out-of-range
        # reflectance and so into NaN, exactly as a mask would.
        sampled = scenes.map(
            lambda image: (
                ee.Image(image)
                .select(names)
                .reproject(crs=CRS, scale=reference_spec.scale_m)
                .sampleRectangle(region=region, defaultValue=0)
            )
        ).getInfo()["features"]
        assert sampled, f"no Landsat 7 scene over the chip in {year}"

        def stack(band: str, features: list[dict[str, Any]] = sampled) -> np.ndarray:
            return np.asarray([f["properties"][band] for f in features], dtype=float)

        expected = reduce_period(
            reference_spec,
            {"nir": stack(bands["nir"]), "red": stack(bands["red"])},
            stack("QA_PIXEL"),
            np.ones(stack("QA_PIXEL").shape[1:], dtype=bool),
            radsat=stack("QA_RADSAT"),
        )
        print(
            f"\n{year}: Earth Engine {observed.values[i]:.4f} "
            f"(n_valid {observed.n_valid_observations[i]}) | reference {expected.value:.4f} "
            f"(n_valid {expected.n_valid_observations}, {expected.n_scenes} scenes)"
        )
        # Pixels on the chip's edge may be in one and not the other (a pixel centre
        # versus a bounding-box rule), so agreement is close, not bit-exact.
        assert observed.values[i] == pytest.approx(expected.value, abs=0.02)
        assert abs(observed.n_valid_observations[i] - expected.n_valid_observations) <= 1
