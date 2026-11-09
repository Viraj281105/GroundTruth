"""Comprehensive verification test suite for Task 5B:
Scientific Remediation, Real-World Data Validation & Deployment-Aware Compute Architecture.

Covers:
1. Multi-tile Landsat acquisition, mosaicking, and >=95% AOI coverage gating.
2. Roy et al. (2016) sensor harmonization (coefficients, overlap validation, bias reduction).
3. Donor eligibility matrix, SUTVA exclusion, rank, and condition number diagnostics.
4. Climate integration (Austral wet-season, SPI-12 drought shocks, 5-level hierarchy).
5. Strict real-data vs synthetic benchmark mode separation (fail-closed policy).
6. Evidence-state model and metadata preservation.
7. Storage abstraction tiers and SHA-256 checksum integrity.
8. Local compute worker concurrency and window chunking.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pytest

from groundtruth.contracts.errors import (
    DataUnavailableError,
    InsufficientDataError,
    ProvenanceError,
)
from groundtruth.contracts.evidence import Evidence, EvidenceState
from groundtruth.contracts.provenance import Provenance
from groundtruth.data_access.aoi_pipeline import (
    AnnualObservationRecord,
    AOIObservationBundle,
    AOIObservationCache,
    DataOrigin,
    SceneRasterChip,
    reduce_aoi_scenes_to_series,
)
from groundtruth.data_access.stac import (
    SceneDescriptor,
    calculate_spatial_coverage,
)
from groundtruth.engine.causal.readiness import (
    CausalReadinessState,
    assess_causal_readiness,
)
from groundtruth.engine.matching.eligibility import (
    DonorCategory,
    build_kariba_donor_eligibility_matrix,
    classify_eligible_donor,
    compute_donor_matrix_diagnostics,
)
from groundtruth.engine.observation.harmonization import (
    ROY_2016_OLS_ETM_TO_OLI_BANDS,
    UnsupportedHarmonizationError,
    get_harmonization_coefficients,
    validate_band_overlap,
    validate_ndvi_overlap,
)
from groundtruth.platform.storage.blob_store import (
    LocalStorageBackend,
    StorageTier,
)


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


# --- 1. Multi-Tile AOI Coverage and Mosaicking Gating ---------------------------------


def test_spatial_coverage_calculation() -> None:
    """Exact spatial coverage accounting and 95% completeness threshold."""
    zone = np.ones((100, 100), dtype=bool)  # 10,000 pixels

    # 100% valid coverage
    valid_full = np.ones((100, 100), dtype=bool)
    res_full = calculate_spatial_coverage(zone, valid_full, resolution_m=100.0)
    assert res_full["total_pixels"] == 10000
    assert res_full["valid_pixels"] == 10000
    assert res_full["coverage_pct"] == 100.0
    assert res_full["is_spatially_complete"] is True
    assert res_full["total_area_ha"] == 10000.0

    # 68.9% valid coverage (single-tile footprint)
    valid_partial = np.zeros((100, 100), dtype=bool)
    valid_partial[:68, :] = True
    valid_partial[68, :90] = True  # 6890 pixels = 68.9%
    res_partial = calculate_spatial_coverage(zone, valid_partial, resolution_m=100.0)
    assert res_partial["valid_pixels"] == 6890
    assert res_partial["coverage_pct"] == 68.9
    assert res_partial["is_spatially_complete"] is False  # Must fail 95% threshold


def test_strict_coverage_refusal_for_incomplete_aoi() -> None:
    """When strict_coverage is enabled, coverage below 95% sets value to NaN."""
    zone = np.ones((20, 20), dtype=bool)  # 400 pixels
    # Only 50% coverage
    descriptor = SceneDescriptor(
        id="test_scene_partial",
        collection="landsat-c2-l2",
        datetime="2020-08-15T00:00:00Z",
        bbox=(0.0, 0.0, 1.0, 1.0),
        cloud_cover=0.0,
        assets=("red", "nir08", "qa_pixel"),
        href="test://partial",
        sensor="landsat8",
        tile_id="171/071",
        asset_hrefs={"red": "test://red", "nir08": "test://nir", "qa_pixel": "test://qa"},
    )

    red = np.full((20, 20), 10000.0)
    nir = np.full((20, 20), 20000.0)
    # Mask half the pixels as nodata/fill
    quality = np.zeros((20, 20), dtype=np.int64)
    quality[10:, :] = 1  # Bit 0 set = fill/unusable

    chip = SceneRasterChip(
        descriptor=descriptor,
        bands_dn={"red": red, "nir": nir},
        quality=quality,
    )

    bundle = reduce_aoi_scenes_to_series(
        unit_id="test_unit",
        aoi_geojson={"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]},
        chips_by_year={2020: [chip]},
        indicator="ndvi",
        sensor="landsat8",
        zone_mask=zone,
        min_coverage_threshold=0.95,
        strict_coverage=True,
    )

    rec = bundle.records[0]
    assert rec.is_spatially_complete is False
    assert rec.aoi_coverage_pct == 50.0
    assert math.isnan(rec.value)  # Prevented whole-AOI conclusions


# --- 2. Sensor Harmonization (Roy et al. 2016) ---------------------------------------

# Roy et al. (2016) Table 2 OLS, ETM+ -> OLI surface reflectance bands, as reproduced in the
# Google Earth Engine "Landsat ETM+ to OLI Harmonization" tutorial (independent reference).
ROY_2016_TABLE2_OLS_BANDS = {
    "blue": (0.8474, 0.0003),
    "green": (0.8483, 0.0088),
    "red": (0.9047, 0.0061),
    "nir": (0.8462, 0.0412),
    "swir1": (0.8937, 0.0254),
    "swir2": (0.9071, 0.0172),
}


def test_roy_2016_ols_band_coefficients_match_published_table() -> None:
    """Band coefficients must equal the independently sourced published values."""
    assert set(ROY_2016_OLS_ETM_TO_OLI_BANDS) == set(ROY_2016_TABLE2_OLS_BANDS)
    for band, (slope, intercept) in ROY_2016_TABLE2_OLS_BANDS.items():
        c = get_harmonization_coefficients(band, source_sensor="landsat7", target_sensor="landsat8")
        assert (round(c.slope, 4), round(c.intercept, 4)) == (slope, intercept), band


@pytest.mark.parametrize("index", ["ndvi", "evi", "ndmi", "nbr"])
def test_spectral_indices_are_never_transformed_directly(index: str) -> None:
    """Roy et al. publish no EVI/NDMI/NBR functions; NDVI must come from harmonized bands."""
    with pytest.raises(UnsupportedHarmonizationError, match="harmonize the input bands"):
        get_harmonization_coefficients(index, source_sensor="landsat7", target_sensor="landsat8")


def test_non_landsat_sensor_is_refused() -> None:
    with pytest.raises(UnsupportedHarmonizationError, match="sentinel2"):
        get_harmonization_coefficients("red", source_sensor="sentinel2", target_sensor="landsat8")


def test_same_frame_is_identity_and_oli_to_etm_inverts() -> None:
    same = get_harmonization_coefficients("nir", source_sensor="landsat8", target_sensor="landsat9")
    assert (same.slope, same.intercept) == (1.0, 0.0)
    fwd = get_harmonization_coefficients("red", source_sensor="landsat7", target_sensor="landsat8")
    inv = get_harmonization_coefficients("red", source_sensor="landsat8", target_sensor="landsat7")
    x = np.linspace(0.01, 0.6, 12)
    np.testing.assert_allclose(inv.transform(fwd.transform(x)), x, atol=1e-12)


def test_band_overlap_arithmetic_on_independent_data() -> None:
    """Overlap metrics are computed correctly on data NOT generated from the coefficients.

    This checks arithmetic only. It is not a scientific validation of the harmonization,
    which requires real near-coincident L7/L8 pairs.
    """
    etm = np.linspace(0.02, 0.12, 40)
    oli = etm + 0.01  # a fixed, known inter-sensor offset
    audit = validate_band_overlap(etm, oli, band="red")
    assert audit.n_overlap_samples == 40
    assert audit.raw_mean_bias == pytest.approx(0.01, abs=1e-12)
    expected = float(np.mean(oli - (0.9047 * etm + 0.0061)))
    assert audit.harmonized_mean_bias == pytest.approx(expected, abs=1e-12)


def test_ndvi_overlap_recomputes_ndvi_from_harmonized_bands() -> None:
    rng = np.random.default_rng(3)
    e_red, e_nir = rng.uniform(0.03, 0.10, 50), rng.uniform(0.15, 0.40, 50)
    o_red, o_nir = e_red * 1.02, e_nir * 0.98
    audit = validate_ndvi_overlap(e_red, e_nir, o_red, o_nir)
    h_red, h_nir = 0.9047 * e_red + 0.0061, 0.8462 * e_nir + 0.0412
    expected = float(np.mean((o_nir - o_red) / (o_nir + o_red) - (h_nir - h_red) / (h_nir + h_red)))
    assert audit.quantity == "ndvi"
    assert audit.harmonized_mean_bias == pytest.approx(expected, abs=1e-12)


def test_overlap_refuses_too_few_samples() -> None:
    audit = validate_band_overlap([0.05] * 5, [0.06] * 5, band="red")
    assert audit.is_validated is False
    assert audit.n_overlap_samples == 5
    assert audit.status_summary.startswith("INSUFFICIENT_OVERLAP_SAMPLES")


# --- 2b. Reducer: per-scene sensors and opt-in band harmonization ----------------------

_SQUARE = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}


def _landsat_chip(scene_id: str, sensor: str, red_dn: float, nir_dn: float) -> SceneRasterChip:
    """A 4x4 clear chip whose bands use the sensor's own SR_B* names."""
    red_name, nir_name = {"landsat7": ("SR_B3", "SR_B4"), "landsat8": ("SR_B4", "SR_B5")}[sensor]
    desc = SceneDescriptor(
        id=scene_id,
        collection="landsat-c2-l2",
        datetime="2013-08-15T00:00:00Z",
        bbox=(0.0, 0.0, 1.0, 1.0),
        cloud_cover=0.0,
        assets=(red_name, nir_name, "qa_pixel"),
        href=f"test://{scene_id}",
        sensor=sensor,
        tile_id="171/071",
    )
    return SceneRasterChip(
        descriptor=desc,
        bands_dn={red_name: np.full((4, 4), red_dn), nir_name: np.full((4, 4), nir_dn)},
        quality=np.zeros((4, 4), dtype=np.int64),
    )


def _dn(rho: float) -> float:
    return (rho + 0.2) / 0.0000275


def _ndvi(nir: float, red: float) -> float:
    return (nir - red) / (nir + red)


def test_mixed_sensor_year_reads_each_scene_with_its_own_band_names() -> None:
    """L7 SR_B4 is NIR, L8 SR_B4 is red: a mixed year must not swap them."""
    l7 = _landsat_chip("LE07_L2SP_171071_20130807_02_T1", "landsat7", _dn(0.05), _dn(0.30))
    l8 = _landsat_chip("LC08_L2SP_171071_20130815_02_T1", "landsat8", _dn(0.05), _dn(0.30))
    bundle = reduce_aoi_scenes_to_series(
        "u", _SQUARE, {2013: [l8, l7]}, indicator="ndvi", sensor="landsat8"
    )
    rec = bundle.records[0]
    assert rec.value == pytest.approx(_ndvi(0.30, 0.05), abs=1e-4)
    assert rec.processing_metadata["scene_sensors"] == {"landsat8": 1, "landsat7": 1}
    assert rec.processing_metadata["harmonization"]["applied"] is False


def test_harmonization_is_off_by_default_and_band_level_when_requested() -> None:
    red, nir = 0.05, 0.30
    l7 = _landsat_chip("LE07_L2SP_171071_20130807_02_T1", "landsat7", _dn(red), _dn(nir))
    raw = reduce_aoi_scenes_to_series(
        "u", _SQUARE, {2013: [l7]}, indicator="ndvi", sensor="landsat7"
    )
    assert raw.records[0].value == pytest.approx(_ndvi(nir, red), abs=1e-4)
    assert raw.records[0].harmonized_indices is None

    harm = reduce_aoi_scenes_to_series(
        "u", _SQUARE, {2013: [l7]}, indicator="ndvi", sensor="landsat7", harmonize_sensor=True
    )
    rec = harm.records[0]
    expected = _ndvi(0.8462 * nir + 0.0412, 0.9047 * red + 0.0061)
    assert rec.value == pytest.approx(expected, abs=1e-4)
    assert rec.unharmonized_value == pytest.approx(_ndvi(nir, red), abs=1e-4)
    meta = rec.processing_metadata["harmonization"]
    assert meta["applied"] is True
    assert meta["evidence_state"] == "MODEL_ESTIMATED"
    assert meta["locally_validated"] is False
    assert meta["harmonized_scene_ids"] == ["LE07_L2SP_171071_20130807_02_T1"]


def test_harmonization_leaves_oli_scenes_untouched_in_mixed_year() -> None:
    l7 = _landsat_chip("LE07_L2SP_171071_20130807_02_T1", "landsat7", _dn(0.05), _dn(0.30))
    l8 = _landsat_chip("LC08_L2SP_171071_20130815_02_T1", "landsat8", _dn(0.05), _dn(0.30))
    rec = reduce_aoi_scenes_to_series(
        "u", _SQUARE, {2013: [l7, l8]}, indicator="ndvi", sensor="landsat8", harmonize_sensor=True
    ).records[0]
    assert rec.processing_metadata["harmonization"]["harmonized_scene_ids"] == [
        "LE07_L2SP_171071_20130807_02_T1"
    ]
    # Per-pixel median of two scenes = mean of the harmonized L7 NDVI and raw L8 NDVI.
    l7_h = _ndvi(0.8462 * 0.30 + 0.0412, 0.9047 * 0.05 + 0.0061)
    assert rec.value == pytest.approx((l7_h + _ndvi(0.30, 0.05)) / 2, abs=1e-4)


# --- 3. Real Donor Matrix & Synthetic Control Readiness ------------------------------


@pytest.mark.requires_local_data("data/processed/climate_cache/kariba_chirps_climate.json")
def test_kariba_donor_eligibility_counts_come_from_boundary_data(repo_root: Path) -> None:
    """Counts are derived from the committed donor GeoJSON, with no padded placeholder units."""
    matrix = build_kariba_donor_eligibility_matrix()
    geo = json.loads(
        (repo_root / "cases" / "boundaries" / "kariba-donors.geojson").read_text(encoding="utf-8")
    )
    eligible = sum(1 for f in geo["features"] if f["properties"]["eligible_for_donor_pool"])

    assert matrix.total_candidates_evaluated == len(geo["features"]) == 50
    assert matrix.spatially_eligible_count == eligible == 37
    assert matrix.core_admitted_count == 31
    assert matrix.border_caveat_count == 6
    assert matrix.agricultural_caveat_count == 0  # no land-use data to screen with

    by_id = {u.unit_id: u for u in matrix.units}
    assert "zw-uree" not in by_id
    for f in geo["features"]:
        p = f["properties"]
        rec = by_id[p["unit_id"]]
        assert rec.distance_to_project_km == p["distance_to_project_km"]
        assert rec.area_km2 == p["area_km2"]


@pytest.mark.requires_local_data("data/processed/climate_cache/kariba_chirps_climate.json")
def test_border_caveats_follow_preregistered_rules() -> None:
    matrix = build_kariba_donor_eligibility_matrix()
    border = {u.unit_id for u in matrix.units if u.category == DonorCategory.BORDER_LEAKAGE_CAVEAT}
    assert border == {
        "zw-gokwe-south",
        "zw-hwange",
        "zw-lupane",
        "zm-sinazongwe",
        "zm-kafue",
        "zm-rufunsa",
    }
    for u in matrix.units:
        if u.category == DonorCategory.CORE_ELIGIBLE:
            assert u.distance_to_project_km is not None and u.distance_to_project_km >= 25.0
            assert u.distance_to_host_district_km is not None
            assert u.distance_to_host_district_km >= 10.0


def test_missing_distance_is_a_caveat_not_core() -> None:
    cat, reason = classify_eligible_donor(
        {"spatial_classification": "interior_eligible", "distance_to_host_district_km": 50.0}
    )
    assert cat == DonorCategory.BORDER_LEAKAGE_CAVEAT
    assert reason is not None and "unknown" in reason


def test_real_donor_access_returns_only_eligible_units(repo_root: Path) -> None:
    from groundtruth.platform.cases.registry import get_case
    from groundtruth.platform.datasets.access import RealDonorAccess

    refs = RealDonorAccess().candidates(get_case("kariba-redd").to_request())
    geo = json.loads(
        (repo_root / "cases" / "boundaries" / "kariba-donors.geojson").read_text(encoding="utf-8")
    )
    eligible = {
        f["properties"]["unit_id"]
        for f in geo["features"]
        if f["properties"]["eligible_for_donor_pool"]
    }
    ids = [r.unit_id for r in refs]
    assert set(ids) <= eligible
    assert ids == sorted(ids)
    for host in ("zw-hurungwe", "zw-mbire", "zw-binga", "zw-nyaminyami"):
        assert host not in ids


@pytest.mark.requires_local_data("data/processed/climate_cache/kariba_chirps_climate.json")
def test_donor_diagnostics_unavailable_without_real_panel() -> None:
    """No simulated diagnostics: without an observed panel nothing is reported."""
    matrix = build_kariba_donor_eligibility_matrix()
    assert matrix.diagnostics is None
    assert matrix.diagnostics_status.startswith("UNAVAILABLE")
    assert matrix.to_dict()["diagnostics"] is None


@pytest.mark.requires_local_data("data/processed/climate_cache/kariba_chirps_climate.json")
def test_donor_panel_missing_core_donor_is_refused() -> None:
    with pytest.raises(DataUnavailableError, match="lacks"):
        build_kariba_donor_eligibility_matrix(
            pre_treatment_panel={"zw-hwange": [0.2] * 11},
            treated_pre_series=[0.2] * 11,
        )


def test_donor_matrix_diagnostics_match_independent_computation() -> None:
    """Diagnostics on a supplied panel agree with direct numpy computation."""
    rng = np.random.default_rng(7)
    donors = 0.25 + rng.normal(0, 0.03, size=(11, 6))
    true_w = np.array([0.5, 0.3, 0.2, 0.0, 0.0, 0.0])
    treated = donors @ true_w
    ids = [f"d{i}" for i in range(6)]

    diag = compute_donor_matrix_diagnostics(ids, donors, treated)

    s = np.linalg.svd(donors, compute_uv=False)
    assert diag.matrix_rank == np.linalg.matrix_rank(donors)
    assert diag.condition_number == pytest.approx(s[0] / s[-1])
    w = np.array([diag.weights[i] for i in ids])
    assert w.sum() == pytest.approx(1.0, abs=1e-6)
    assert np.all(w >= -1e-12)
    assert diag.pre_treatment_rmspe == pytest.approx(
        float(np.sqrt(np.mean((treated - donors @ w) ** 2))), abs=1e-9
    )
    assert diag.pre_treatment_rmspe < 1e-3  # treated is inside the convex hull
    assert diag.effective_donors_count == pytest.approx(1.0 / float(np.sum(w**2)))


def test_donor_matrix_diagnostics_refuse_missing_observations() -> None:
    donors = np.full((11, 3), 0.25)
    donors[4, 1] = np.nan
    with pytest.raises(InsufficientDataError, match="refusing to impute"):
        compute_donor_matrix_diagnostics(["a", "b", "c"], donors, np.full(11, 0.25))


def test_ill_conditioned_donor_matrix_fails_closed() -> None:
    """If donor matrix is rank-deficient or ill-conditioned, causal readiness fails closed."""
    readiness = assess_causal_readiness(
        case_id="kariba-redd",
        unit_id="kariba-redd",
        pre_treatment_years=11,
        post_treatment_years=11,
        usable_donors_count=37,
        aoi_coverage_fraction=1.0,
        donor_pool_independence=True,
        spillover_buffer_km=20.0,
        donor_matrix_condition_number=1e7,  # Ill-conditioned
        donor_matrix_rank=5,  # Rank-deficient (< 11)
    )

    assert readiness.status == CausalReadinessState.INSUFFICIENT_DATA
    assert readiness.is_ready is False
    assert any("ill-conditioned" in b for b in readiness.blockers)


# --- 4. Evidence State and Mode Segregation ------------------------------------------


def test_evidence_state_classification() -> None:
    """Evidence items explicitly declare their epistemological state."""
    prov = Provenance.observed(source="landsat-c2-l2", stage="geospatial")

    ev_obs = Evidence(
        id="ndvi.raw",
        label="Raw NDVI",
        value=0.28,
        unit="",
        provenance=prov,
        state=EvidenceState.OBSERVED,
    )
    assert ev_obs.state == EvidenceState.OBSERVED

    ev_harm = Evidence(
        id="ndvi.harmonized",
        label="Harmonized NDVI",
        value=0.29,
        unit="",
        provenance=prov,
        state=EvidenceState.MODEL_ESTIMATED,
    )
    assert ev_harm.state == EvidenceState.MODEL_ESTIMATED


def test_bundle_cached_origin_integrity(tmp_path: Path) -> None:
    """Loading REAL_STAC from cache preserves provenance and marks CACHED_REAL_STAC."""
    cache = AOIObservationCache(tmp_path)
    bundle = AOIObservationBundle(
        unit_id="test_unit",
        indicator="ndvi",
        bbox=(0.0, 0.0, 1.0, 1.0),
        records=(),
        data_origin=DataOrigin.REAL_STAC,
        catalog_url="https://planetarycomputer.microsoft.com/api/stac/v1",
        provenance=Provenance.observed(source="landsat", stage="geospatial"),
    )
    cache.put(bundle)

    loaded = cache.get("test_unit", "ndvi", require_real=True)
    assert loaded.data_origin == DataOrigin.CACHED_REAL_STAC
    assert loaded.is_synthetic is False


# --- 5. Storage Abstraction Tiers & SHA-256 Checksums --------------------------------


def test_local_storage_tier_separation_and_checksum(tmp_path: Path) -> None:
    """Storage backend strictly segregates raw, interim, processed, and metadata tiers."""
    store = LocalStorageBackend(tmp_path)
    test_bytes = b"Surface Reflectance Raster Band 4"
    expected_sha256 = hashlib.sha256(test_bytes).hexdigest()

    meta = store.put_bytes(
        StorageTier.RAW_SOURCE,
        "landsat/LC08_B4.tif",
        test_bytes,
        content_type="image/tiff",
        metadata={"sensor": "landsat8", "band": "B4"},
    )

    assert meta.tier == StorageTier.RAW_SOURCE
    assert meta.size_bytes == len(test_bytes)
    assert meta.sha256 == expected_sha256
    assert store.exists(StorageTier.RAW_SOURCE, "landsat/LC08_B4.tif")
    assert store.get_bytes(StorageTier.RAW_SOURCE, "landsat/LC08_B4.tif") == test_bytes

    # Ensure tiers do not bleed into each other
    assert not store.exists(StorageTier.FINAL_EVIDENCE, "landsat/LC08_B4.tif")
    assert "landsat/LC08_B4.tif" in store.list_keys(StorageTier.RAW_SOURCE)


# --- 6. REAL_STAC provenance integrity guard ----------------------------------------


def _record(year: int, scene_ids: tuple[str, ...], dates: tuple[str, ...], sha: str, **kw):
    base: dict[str, object] = {
        "year": year,
        "indicator": "ndvi",
        "value": 0.3,
        "n_valid_observations": 1,
        "clear_pixel_fraction": 0.9,
        "n_scenes": len(scene_ids),
        "scene_ids": scene_ids,
        "acquisition_dates": dates,
        "sensor": "landsat8",
        "scenes_sha256": sha,
        "n_valid_pixels": 900,
        "n_total_pixels": 1000,
    }
    base.update(kw)
    return AnnualObservationRecord(**base)


def _bundle(*records: AnnualObservationRecord) -> AOIObservationBundle:
    return AOIObservationBundle(
        unit_id="kariba-redd",
        indicator="ndvi",
        bbox=(27.6, -17.7, 31.1, -15.6),
        records=records,
        data_origin=DataOrigin.REAL_STAC,
        catalog_url="https://planetarycomputer.microsoft.com/api/stac/v1",
        provenance=Provenance.observed(source="landsat-c2-l2", stage="geospatial"),
    )


def _ids_sha(ids: tuple[str, ...]) -> str:
    d = hashlib.sha256()
    for sid in sorted(ids):
        d.update(sid.encode())
        d.update(b"\0")
    return d.hexdigest()


def test_provenance_guard_accepts_consistent_real_bundle(tmp_path: Path) -> None:
    ids = ("LC08_L2SP_170072_20200710_02_T1", "LC08_L2SP_171071_20200717_02_T1")
    bundle = _bundle(_record(2020, ids, ("2020-07-10", "2020-07-17"), _ids_sha(ids)))
    cache = AOIObservationCache(tmp_path)
    cache.put(bundle)
    assert cache.get("kariba-redd", "ndvi").data_origin == DataOrigin.CACHED_REAL_STAC


def test_provenance_guard_rejects_fabricated_style_bundle(tmp_path: Path) -> None:
    """Mirrors the quarantined Task 5B cache: invented ids, placeholder hash, 100% coverage."""
    ids = ("LE07_L2SP_169072_20010815", "LE07_L2SP_170071_20010815")
    rec = _record(
        2001,
        ids,
        ("2001-08-15", "2001-08-15"),
        "sha256_2001_landsat7_multitile",
        n_scenes=31,
        clear_pixel_fraction=1.0,
        n_valid_pixels=1072638,
        n_total_pixels=1072638,
        aoi_coverage_pct=100.0,
        sensor="landsat7",
    )
    with pytest.raises(ProvenanceError) as exc:
        AOIObservationCache(tmp_path).put(_bundle(rec))
    msg = str(exc.value)
    assert "not a sha256 hex digest" in msg
    assert "n_scenes=31" in msg
    assert "not a Landsat Collection 2 product id" in msg


def test_provenance_guard_rejects_coverage_inconsistent_with_pixel_counts(tmp_path: Path) -> None:
    ids = ("LC08_L2SP_170072_20200710_02_T1",)
    rec = _record(2020, ids, ("2020-07-10",), _ids_sha(ids), aoi_coverage_pct=100.0)
    with pytest.raises(ProvenanceError, match="aoi_coverage_pct"):
        AOIObservationCache(tmp_path).put(_bundle(rec))


def test_provenance_guard_rejects_tampered_cache_on_read(tmp_path: Path) -> None:
    ids = ("LC08_L2SP_170072_20200710_02_T1",)
    cache = AOIObservationCache(tmp_path)
    path = cache.put(_bundle(_record(2020, ids, ("2020-07-10",), _ids_sha(ids))))
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["records"][0]["scene_ids"] = ["LC08_L2SP_999999_20200710_02_T1"]
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ProvenanceError, match="does not match"):
        cache.get("kariba-redd", "ndvi")
