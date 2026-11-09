"""Unit and integration test suite for Task 5: Real-World Evidence Acquisition & Historical Data Recovery.

Tests:
1. Data discovery registry completeness (100+ sources, 10 domains, 18 fields, strict statuses).
2. USGS Landsat Collection 2 Level-2 surface reflectance scaling and QA pixel masking.
3. Planetary Computer asset resolution and multi-sensor support (Landsat 5, 7, 8, 9).
4. Strict fail-closed policy (no silent fallback to synthetic fixtures in real data mode).
5. Explicit synthetic benchmark labelling.
6. Causal readiness evaluation engine and multi-criterion gates.
7. Real donor pool audit completeness.
8. API endpoints: /cases/{id}/causal-readiness and /cases/{id}/real-observations.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from groundtruth.contracts.errors import DataUnavailableError
from groundtruth.contracts.evidence import EvidenceState
from groundtruth.data_access.aoi_pipeline import _resolve_sensor
from groundtruth.engine.causal.readiness import (
    CausalReadinessState,
    assess_causal_readiness,
)
from groundtruth.engine.observation.reduction import (
    SENSORS,
    qa_pixel_mask,
    to_reflectance,
)
from groundtruth.platform.api.app import app
from groundtruth.platform.cases.registry import get_case
from groundtruth.platform.datasets.access import (
    earth_engine_access,
    get_data_access,
)


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


# --- 1. Source Registry Tests ---------------------------------------------------------


def test_source_registry_completeness(repo_root: Path) -> None:
    """Registry must contain >= 100 authoritative environmental datasets across domains A-J."""
    registry_path = repo_root / "data" / "catalog" / "source_registry.json"
    assert registry_path.is_file(), f"Source registry not found at {registry_path}"

    catalog = json.loads(registry_path.read_text(encoding="utf-8"))
    entries = catalog.get("sources", [])
    assert len(entries) >= 100, f"Expected >= 100 entries, found {len(entries)}"

    required_fields = {
        "id",
        "name",
        "provider",
        "official_url",
        "domain",
        "geographic_coverage",
        "temporal_coverage",
        "spatial_resolution",
        "temporal_resolution",
        "access_mechanism",
        "api_stac_download_availability",
        "licensing",
        "auth_requirements",
        "update_frequency",
        "expected_usefulness",
        "is_independent",
        "integration_status",
        "feasibility_for_kariba",
    }

    valid_statuses = {
        "DISCOVERED",
        "ACCESS_VERIFIED",
        "SAMPLE_RETRIEVED",
        "QUALITY_VALIDATED",
        "INTEGRATED",
        "UNAVAILABLE",
        "REQUIRES_AUTHENTICATION",
    }

    domains_found = set()
    for entry in entries:
        missing = required_fields - set(entry.keys())
        assert not missing, f"Entry {entry.get('name')} missing fields: {missing}"
        assert entry["integration_status"] in valid_statuses
        domains_found.add(entry["domain"])

    # Must cover at least 10 environmental domains
    assert len(domains_found) >= 10, f"Expected >= 10 distinct domains, found {domains_found}"


# --- 2. Landsat Scaling and QA Masking ------------------------------------------------


def test_landsat_surface_reflectance_scaling() -> None:
    """Landsat C2 Level-2 scaling formula: rho = DN * 0.0000275 - 0.2."""
    sensor = SENSORS["landsat8"]
    # DN = 7273 corresponds to rho = 0.0
    # DN = 25455 corresponds to rho = 0.5
    raw_dn = np.array([[7273, 25455], [0, 50000]], dtype=np.uint16)
    scaled = to_reflectance(raw_dn, sensor)

    assert scaled.shape == (2, 2)
    assert np.isclose(scaled[0, 0], 0.0, atol=1e-3)
    assert np.isclose(scaled[0, 1], 0.5, atol=1e-3)
    # DN = 0 yields negative reflectance (-0.2), which to_reflectance maps to NaN
    assert np.isnan(scaled[1, 0])


def test_landsat_qa_pixel_masking_slc_and_clouds() -> None:
    """QA_PIXEL bits: 0=fill (SLC-off), 1=dilated cloud, 3=cloud, 4=cloud shadow."""
    # Pixel 0: Clear (0) -> True (valid)
    # Pixel 1: Fill / SLC-off (bit 0 = 1) -> False (invalid)
    # Pixel 2: Cloud (bit 3 = 8) -> False (invalid)
    # Pixel 3: Cloud shadow (bit 4 = 16) -> False (invalid)
    qa = np.array([[0, 1], [8, 16]], dtype=np.uint16)
    valid_mask = qa_pixel_mask(qa)

    assert valid_mask[0, 0]
    assert not valid_mask[0, 1]
    assert not valid_mask[1, 0]
    assert not valid_mask[1, 1]


def test_qa_radsat_saturation_masking() -> None:
    """QA_RADSAT: non-zero values indicate band saturation and are masked."""
    qa = np.array([[0, 0], [0, 0]], dtype=np.uint16)
    radsat = np.array([[0, 2], [0, 4]], dtype=np.uint16)
    valid_mask = qa_pixel_mask(qa, radsat=radsat)

    assert valid_mask[0, 0]
    assert not valid_mask[0, 1]
    assert valid_mask[1, 0]
    assert not valid_mask[1, 1]


# --- 3. Planetary Computer Sensor Specs ----------------------------------------------


def test_sensor_specs_landsat_family() -> None:
    """Platform detection must support Landsat 5, 7, 8, 9 and Sentinel-2."""
    for platform in ["landsat-5", "landsat-7", "landsat-8", "landsat-9", "sentinel-2"]:
        spec = _resolve_sensor(platform)
        assert spec.sensor.startswith("landsat") or spec.sensor == "sentinel2"
        assert "red" in spec.bands
        assert "nir" in spec.bands
        assert spec.reflectance_scale > 0.0


# --- 4. Evidence State Enum Contract -------------------------------------------------


def test_evidence_state_enum_vocabulary() -> None:
    """EvidenceState must strictly separate observed from derived or inferred evidence."""
    assert EvidenceState.OBSERVED == "OBSERVED"
    assert EvidenceState.DERIVED == "DERIVED"
    assert EvidenceState.MODEL_ESTIMATED == "MODEL_ESTIMATED"
    assert EvidenceState.INFERRED == "INFERRED"
    assert EvidenceState.UNAVAILABLE == "UNAVAILABLE"
    assert EvidenceState.INSUFFICIENT_EVIDENCE == "INSUFFICIENT_EVIDENCE"


# --- 5. Fail-Closed Policy (No Silent Fallback to Synthetic) --------------------------


def test_earth_engine_access_fails_closed_without_synthetic_fallback() -> None:
    """In real data mode, incomplete or unverified data raises DataUnavailableError.

    Silent fallback to synthetic fixtures is strictly prohibited.
    """
    request = get_case("kariba-redd").to_request(data_mode="observed")

    with pytest.raises(DataUnavailableError) as exc_info:
        earth_engine_access(request)

    error_msg = str(exc_info.value)
    assert "not implemented" in error_msg
    assert "PARTIALLY_READY" in error_msg
    assert "silent fallback to synthetic fixtures is strictly prohibited" in error_msg


def test_get_data_access_mode_dispatch() -> None:
    """get_data_access must strictly dispatch between real mode and synthetic benchmark mode."""
    request = get_case("kariba-redd").to_request()

    # Real mode fails closed rather than returning synthetic fixtures
    with pytest.raises(DataUnavailableError):
        get_data_access(request, mode="REAL_OBSERVATIONS")

    # Synthetic benchmark mode explicitly returns synthetic fixture access
    syn_access = get_data_access(request, mode="SYNTHETIC_BENCHMARK")
    assert syn_access.observations is not None
    prov = syn_access.observations.provenance(None)
    assert "SYNTHETIC" in prov.source.upper() or "SYNTHETIC" in prov.notes.upper()


# --- 6. Causal Readiness Assessment Engine -------------------------------------------


def test_causal_readiness_blocker_detection() -> None:
    """Readiness engine flags insufficient pre-treatment baseline or donor units."""
    # Under-identified baseline (3 years < 5 years required)
    rep = assess_causal_readiness(
        case_id="test-case",
        unit_id="test-unit",
        pre_treatment_years=3,
        post_treatment_years=5,
        usable_donors_count=20,
        aoi_coverage_fraction=0.95,
        donor_pool_independence=True,
        spillover_buffer_km=25.0,
    )
    assert rep.status == CausalReadinessState.INSUFFICIENT_DATA
    assert not rep.is_ready
    assert any("Pre-treatment duration" in b for b in rep.blockers)

    # Spatial coverage blocker (< 50%)
    rep_spatial = assess_causal_readiness(
        case_id="test-case",
        unit_id="test-unit",
        pre_treatment_years=10,
        post_treatment_years=5,
        usable_donors_count=20,
        aoi_coverage_fraction=0.35,
        donor_pool_independence=True,
        spillover_buffer_km=25.0,
    )
    assert rep_spatial.status == CausalReadinessState.INSUFFICIENT_DATA
    assert any("covers only 35.0%" in b for b in rep_spatial.blockers)


def test_causal_readiness_kariba_partially_ready() -> None:
    """Kariba real data configuration evaluates to PARTIALLY_READY due to sensor & climate caveats."""
    rep = assess_causal_readiness(
        case_id="kariba-redd",
        unit_id="kariba-redd",
        pre_treatment_years=11,
        post_treatment_years=11,
        usable_donors_count=37,
        aoi_coverage_fraction=0.689,
        donor_pool_independence=True,
        spillover_buffer_km=20.0,
        sensor_discontinuity_present=True,
        slc_off_missingness_pct=22.0,
        severe_climate_confounding_detected=True,
    )
    assert rep.status == CausalReadinessState.PARTIALLY_READY
    assert not rep.is_ready
    assert len(rep.blockers) == 0
    assert len(rep.warnings) >= 2
    assert "PARTIALLY_READY" in rep.status.value


# --- 7. Donor Pool Audit Completeness ------------------------------------------------


@pytest.mark.requires_local_data("data/processed/donor_landsat_coverage_audit.json")
def test_donor_pool_audit_records(repo_root: Path) -> None:
    """Audit records must confirm 37 donors with 100% observable benchmark epochs."""
    audit_path = repo_root / "data" / "processed" / "donor_landsat_coverage_audit.json"
    assert audit_path.is_file(), "Donor audit JSON not found"

    donors = json.loads(audit_path.read_text(encoding="utf-8"))
    assert len(donors) == 37, f"Expected 37 donors, found {len(donors)}"

    for _unit_id, info in donors.items():
        assert info["all_benchmarks_observable"] is True
        benchmarks = info["benchmarks"]
        for year in ["2001", "2005", "2010", "2015", "2022"]:
            assert year in benchmarks
            assert benchmarks[year]["n_scenes"] > 0
            assert benchmarks[year]["min_cloud"] <= 15.0


# --- 8. API Endpoints ----------------------------------------------------------------


def test_hardcoded_endpoints_removed() -> None:
    """The two endpoints that served hand-entered numbers no longer exist (404, any caller)."""
    client = TestClient(app)
    for suffix in ("causal-readiness", "real-observations"):
        assert client.get(f"/cases/kariba-redd/{suffix}").status_code == 404
