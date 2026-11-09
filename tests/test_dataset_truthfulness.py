"""Tests for Dataset Integration Truthfulness, Lifecycle Gates, and Provenance."""

from __future__ import annotations

import pytest

from groundtruth.platform.datasets.evidence_registry import (
    SourceLifecycle,
    get_global_evidence_registry,
)


def test_quarantined_dataset_fails_closed():
    """Verify quarantined datasets are blocked from operational access fail-closed."""
    registry = get_global_evidence_registry()
    quarantined = registry.get_source("quarantined-legacy-landsat-cache")
    assert quarantined is not None
    assert quarantined.lifecycle == SourceLifecycle.QUARANTINED
    assert quarantined.is_operational_integration is False
    assert quarantined.quarantine_reason is not None

    with pytest.raises(PermissionError, match=r"QUARANTINED.*fail-closed"):
        registry.assert_operational("quarantined-legacy-landsat-cache")


def test_discovered_and_accessible_datasets_cannot_enter_production():
    """Verify discovered and accessible datasets are blocked from operational analytical pipelines."""
    registry = get_global_evidence_registry()

    # Discovered Sentinel-1 GRD
    s1 = registry.get_source("sentinel-1-grd-c-band")
    assert s1 is not None
    assert s1.lifecycle == SourceLifecycle.DISCOVERED
    assert s1.is_operational_integration is False
    assert s1.ingestion_mode == "scaffolded_catalog"
    with pytest.raises(
        PermissionError, match="Discovered and accessible datasets cannot enter production"
    ):
        registry.assert_operational("sentinel-1-grd-c-band")

    # Accessible Landsat C2 L2
    landsat = registry.get_source("landsat-c2-l2-sr")
    assert landsat is not None
    assert landsat.lifecycle == SourceLifecycle.ACCESSIBLE
    assert landsat.is_operational_integration is False
    assert landsat.ingestion_mode == "accessible_endpoint"
    with pytest.raises(
        PermissionError, match="Discovered and accessible datasets cannot enter production"
    ):
        registry.assert_operational("landsat-c2-l2-sr")


def test_automated_vs_manual_staging_distinction():
    """Verify fully automated pipelines are distinguished from manual staging."""
    registry = get_global_evidence_registry()

    # Automated pipelines
    s2 = registry.assert_operational("sentinel-2-msi-l2a")
    assert s2.ingestion_mode == "automated_pipeline"
    assert s2.lifecycle == SourceLifecycle.VALIDATED

    chirps = registry.assert_operational("chirps-monthly-v2")
    assert chirps.ingestion_mode == "automated_pipeline"
    assert chirps.lifecycle == SourceLifecycle.VALIDATED

    # Manual staging - GEDI LiDAR
    gedi = registry.assert_operational("gedi-l4a-footprint-biomass")
    assert gedi.ingestion_mode == "manual_staging"
    assert "MANUAL STAGING" in gedi.notes
    assert "not deployed" in gedi.notes or "NOT deployed" in gedi.notes

    # Manual staging - ALOS-2 SAR
    palsar = registry.assert_operational("alos2-palsar-sar-mosaic")
    assert palsar.ingestion_mode == "manual_staging"
    assert "MANUAL STAGING" in palsar.notes


def test_dataset_licensing_and_permitted_use_visible():
    """Verify every registered source has explicit licensing and permitted usage defined."""
    registry = get_global_evidence_registry()
    sources = registry.list_sources()

    assert len(sources) >= 8
    for s in sources:
        assert s.license, f"Source {s.source_id} missing license"
        assert s.permitted_usage, f"Source {s.source_id} missing permitted_usage"
        assert s.content_hash.startswith("sha256:"), f"Source {s.source_id} invalid content_hash"
        assert s.provider, f"Source {s.source_id} missing provider"
        assert s.source_url.startswith("http") or s.source_url.startswith("s3")
