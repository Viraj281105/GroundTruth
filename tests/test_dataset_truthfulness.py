"""Tests for dataset registry truthfulness, lifecycle gates, provenance and health consistency."""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from groundtruth.contracts.errors import DataUnavailableError
from groundtruth.platform.api.app import app
from groundtruth.platform.datasets.evidence_registry import (
    EvidenceRegistry,
    IngestionMode,
    ModalityType,
    ProductionAnalysisBlockedError,
    SourceLifecycle,
    ValidationStatus,
    assert_dataset_allowed_for_production,
    get_global_evidence_registry,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "packages" / "groundtruth" / "src" / "groundtruth"


def _registry() -> EvidenceRegistry:
    return get_global_evidence_registry()


def test_quarantined_dataset_fails_closed():
    registry = _registry()
    quarantined = registry.get_source("quarantined-legacy-landsat-cache")
    assert quarantined is not None
    assert quarantined.lifecycle == SourceLifecycle.QUARANTINED
    assert quarantined.ingestion_mode == IngestionMode.QUARANTINED
    assert quarantined.validation_status == ValidationStatus.FAILED
    assert quarantined.is_operational_integration is False
    assert quarantined.quarantine_reason is not None
    assert quarantined.blocked_for_production_analysis is True

    with pytest.raises(PermissionError, match=r"QUARANTINED.*fail-closed"):
        registry.assert_operational("quarantined-legacy-landsat-cache")
    with pytest.raises(ProductionAnalysisBlockedError, match="QUARANTINED"):
        assert_dataset_allowed_for_production("quarantined-legacy-landsat-cache")


def test_discovered_and_accessible_datasets_cannot_enter_production():
    registry = _registry()

    s1 = registry.get_source("sentinel-1-grd-c-band")
    assert s1 is not None
    assert s1.lifecycle == SourceLifecycle.DISCOVERED
    assert s1.is_operational_integration is False
    assert s1.ingestion_mode == IngestionMode.SCAFFOLDED
    with pytest.raises(
        PermissionError, match="Discovered and accessible datasets cannot enter production"
    ):
        registry.assert_operational("sentinel-1-grd-c-band")

    landsat = registry.get_source("landsat-c2-l2-sr")
    assert landsat is not None
    assert landsat.lifecycle == SourceLifecycle.ACCESSIBLE
    assert landsat.is_operational_integration is False
    assert landsat.ingestion_mode == IngestionMode.ACCESSIBLE_UNVALIDATED
    with pytest.raises(
        PermissionError, match="Discovered and accessible datasets cannot enter production"
    ):
        registry.assert_operational("landsat-c2-l2-sr")


def test_no_source_claims_operational_without_automated_validated_ingestion():
    """is_operational_integration is True only for automated_operational + validated + unblocked."""
    for s in _registry().list_sources():
        if s.is_operational_integration:
            assert s.ingestion_mode == IngestionMode.AUTOMATED_OPERATIONAL, s.source_id
            assert s.validation_status == ValidationStatus.VALIDATED, s.source_id
            assert not s.blocked_for_production_analysis, s.source_id
        if s.ingestion_mode == IngestionMode.AUTOMATED_OPERATIONAL:
            # An automated pipeline must actually exist in code: nothing in this repo schedules
            # one, so no registered source may claim it until that changes.
            pytest.fail(f"{s.source_id} claims automated_operational but no scheduler exists")


def test_registry_rejects_dishonest_entries():
    base = _registry().get_source("sentinel-2-msi-l2a")
    assert base is not None
    with pytest.raises(ValueError, match="is_operational_integration"):
        dataclasses.replace(base, is_operational_integration=True)
    with pytest.raises(ValueError, match="unmeasured quality"):
        dataclasses.replace(base, data_quality_score=99.2)
    with pytest.raises(ValueError, match="retrieval_timestamp"):
        dataclasses.replace(base, retrieval_status="not_retrieved")
    with pytest.raises(ValueError, match="sha256"):
        dataclasses.replace(base, content_hash="sha256:abc")
    with pytest.raises(ValueError):
        dataclasses.replace(base, ingestion_mode="automated_pipeline")  # stale vocabulary
    with pytest.raises(ValueError, match="validation_evidence"):
        dataclasses.replace(
            base, validation_status=ValidationStatus.VALIDATED, validation_evidence="none"
        )


def test_synthetic_benchmark_is_never_operational_or_scored():
    synth = _registry().get_source("synthetic-kariba-benchmark")
    assert synth is not None
    assert synth.modality == ModalityType.SYNTHETIC_BENCHMARK
    assert synth.ingestion_mode == IngestionMode.SYNTHETIC_SIMULATED
    assert synth.is_operational_integration is False
    assert synth.lifecycle != SourceLifecycle.VALIDATED
    assert synth.data_quality_score is None and synth.completeness_percentage is None
    assert synth.blocked_for_production_analysis is True
    assert "SYNTHETIC" in synth.title.upper()
    with pytest.raises(ProductionAnalysisBlockedError, match="synthetic"):
        assert_dataset_allowed_for_production("synthetic-kariba-benchmark")


def test_unsupported_datasets_are_blocked_from_production():
    for source_id in (
        "sentinel-2-msi-l2a",
        "landsat-c2-l2-sr",
        "sentinel-1-grd-c-band",
        "gedi-l4a-footprint-biomass",
        "alos2-palsar-sar-mosaic",
        "synthetic-kariba-benchmark",
        "quarantined-legacy-landsat-cache",
    ):
        with pytest.raises(ProductionAnalysisBlockedError):
            assert_dataset_allowed_for_production(source_id)
    with pytest.raises(ProductionAnalysisBlockedError, match="not in the evidence registry"):
        assert_dataset_allowed_for_production("does-not-exist")
    # Guard errors map to the DataUnavailable family (fail-closed, HTTP 501/503 path).
    assert issubclass(ProductionAnalysisBlockedError, DataUnavailableError)


def test_staged_real_artifacts_may_be_used_and_missing_artifacts_block():
    registry = _registry()
    for source_id in (
        "chirps-monthly-v2",
        "nasa-power-temperatures",
        "geoboundaries-adm2-zimbabwe",
    ):
        src = registry.get_source(source_id)
        assert src is not None
        assert src.is_operational_integration is False
        assert src.ingestion_mode in (IngestionMode.MANUAL_STAGING, IngestionMode.CURATED_VECTOR)
        registry.assert_dataset_allowed_for_production(source_id)

    chirps = registry.get_source("chirps-monthly-v2")
    assert chirps is not None
    gone = dataclasses.replace(chirps, local_artifact_paths=("data/does/not/exist.json",))
    private = EvidenceRegistry([gone])
    with pytest.raises(ProductionAnalysisBlockedError, match="artefacts are missing"):
        private.assert_dataset_allowed_for_production("chirps-monthly-v2")


def test_earth_engine_access_registry_gate_blocks_sentinel2(monkeypatch):
    """Even when readiness passes, the registry gate refuses blocked datasets."""
    from groundtruth.engine.causal import readiness as readiness_mod
    from groundtruth.platform.cases.registry import get_case
    from groundtruth.platform.datasets import access

    class _Ready:
        is_ready = True

    monkeypatch.setattr(readiness_mod, "assess_causal_readiness", lambda **_: _Ready())
    request = get_case("kariba-redd").to_request(data_mode="observed")
    with pytest.raises(ProductionAnalysisBlockedError, match="sentinel-2-msi-l2a"):
        access.earth_engine_access(request)


def test_summary_statistics_reflect_truthful_flags():
    registry = _registry()
    stats = registry.get_summary_statistics()
    sources = registry.list_sources()
    assert stats["total_registered"] == len(sources)
    assert stats["operational_count"] == sum(s.is_operational_integration for s in sources) == 0
    assert stats["validated"] == sum(s.lifecycle == SourceLifecycle.VALIDATED for s in sources)
    assert stats["blocked_count"] + stats["usable_for_production_count"] == len(sources)
    assert stats["synthetic_count"] == 1
    measured = [s.completeness_percentage for s in sources if s.quality_measured]
    assert stats["completeness_measured_count"] == len(measured)
    # Unmeasured sources must not drag an invented mean in.
    assert EvidenceRegistry([]).get_summary_statistics()["average_completeness"] is None


def test_unmeasured_quality_and_retrieval_are_null_not_invented():
    for s in _registry().list_sources():
        if not s.quality_measured:
            assert s.data_quality_score is None and s.completeness_percentage is None, s.source_id
        if s.retrieval_status == "not_retrieved":
            assert s.retrieval_timestamp is None, s.source_id
        if s.content_hash is not None:
            assert re.fullmatch(r"sha256:[0-9a-f]{64}", s.content_hash), s.source_id
            assert s.content_hash_scope, f"{s.source_id}: real hash must name what it hashes"
    for source_id in ("gedi-l4a-footprint-biomass", "alos2-palsar-sar-mosaic"):
        s = _registry().get_source(source_id)
        assert s is not None
        assert s.retrieval_timestamp is None and s.content_hash is None
        assert s.retrieval_status == "not_retrieved"


def test_declared_content_hash_matches_artifact_on_disk():
    import hashlib

    for s in _registry().list_sources():
        if s.content_hash and s.content_hash_scope:
            rel = s.content_hash_scope.split(" ")[0]
            digest = hashlib.sha256((REPO_ROOT / rel).read_bytes()).hexdigest()
            assert s.content_hash == f"sha256:{digest}", s.source_id


def test_dataset_provenance_fields_visible_and_licensed():
    sources = _registry().list_sources()
    assert len(sources) >= 8
    for s in sources:
        assert s.license, f"Source {s.source_id} missing license"
        assert s.permitted_usage, f"Source {s.source_id} missing permitted_usage"
        assert s.provider and s.version and s.dataset_identifier
        assert s.spatial_coverage and s.temporal_coverage_start and s.temporal_coverage_end
        assert s.source_url.startswith("http")
        assert s.validation_evidence, s.source_id
        assert s.blocked_for_production_analysis == bool(s.blocked_reason), s.source_id


def test_climate_registry_uses_bundle_facts_not_invented_gaps():
    chirps = _registry().get_source("chirps-monthly-v2")
    assert chirps is not None
    assert "2022.07" in chirps.missingness_summary  # real missing month from the bundle
    assert "1994" not in chirps.missingness_summary  # previously invented


# --- API / health consistency ---------------------------------------------------------


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_health_is_derived_from_registry(client):
    health = client.get("/health").json()
    stats = _registry().get_summary_statistics()
    assert health["earth_observation_implemented"] is _registry().earth_observation_implemented()
    assert health["earth_observation_implemented"] is False
    assert health["evidence_sources_total"] == stats["total_registered"]
    assert health["evidence_sources_operational"] == stats["operational_count"] == 0
    assert health["evidence_sources_usable_for_production"] == stats["usable_for_production_count"]
    # Health and registry can no longer disagree: no operational source <=> no EO.
    reg = client.get("/evidence-registry").json()
    assert (reg["operational_count"] > 0) == health["earth_observation_implemented"]
    assert health["engine_capabilities"]["cross_sensor_calibration"] is False


def test_registry_api_schema_and_truthfulness(client):
    res = client.get("/evidence-registry")
    assert res.status_code == 200
    data = res.json()
    assert data["operational_count"] == 0
    assert data["ingestion_mode_counts"]["synthetic_simulated"] == 1
    required = {
        "ingestion_mode",
        "validation_status",
        "validation_evidence",
        "blocked_for_production_analysis",
        "blocked_reason",
        "quality_measured",
        "retrieval_status",
        "retrieval_provenance",
        "content_hash_scope",
        "source_url",
        "version",
        "license",
        "spatial_coverage",
        "temporal_coverage_start",
    }
    by_id = {s["source_id"]: s for s in data["sources"]}
    for s in data["sources"]:
        assert required <= s.keys()
        assert s["is_operational_integration"] is False
    synth = by_id["synthetic-kariba-benchmark"]
    assert synth["ingestion_mode"] == "synthetic_simulated"
    assert synth["data_quality_score"] is None and synth["blocked_for_production_analysis"]
    assert by_id["gedi-l4a-footprint-biomass"]["retrieval_timestamp"] is None
    assert by_id["sentinel-2-msi-l2a"]["blocked_for_production_analysis"] is True
    assert by_id["quarantined-legacy-landsat-cache"]["validation_status"] == "failed"
    assert by_id["chirps-monthly-v2"]["completeness_percentage"] is not None
    assert by_id["chirps-monthly-v2"]["quality_measured"] is True

    assert client.get("/evidence-registry/does-not-exist").status_code == 404
    one = client.get("/evidence-registry/geoboundaries-adm2-zimbabwe").json()
    assert one["ingestion_mode"] == "curated_vector"


def test_registry_is_public_reference_metadata_only(client):
    """Unauthenticated by design: the payload may carry no tenant, user or project data."""
    body = client.get("/evidence-registry").text.lower()
    for marker in ("organization_id", "org_id", "user_id", "email", "password", "tenant"):
        assert marker not in body
    # Registry sources are static module data, not DB rows.
    src = (SRC / "platform" / "datasets" / "evidence_registry.py").read_text(encoding="utf-8")
    assert "sqlalchemy" not in src and "Session" not in src
