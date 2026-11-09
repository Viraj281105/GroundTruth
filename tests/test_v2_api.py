"""Tests for GroundTruth 2.0 API Endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from groundtruth.platform.api.app import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_evidence_registry_lists_all_and_filters(client):
    res = client.get("/evidence-registry")
    assert res.status_code == 200
    data = res.json()
    assert data["total_registered"] >= 7
    assert data["operational_count"] >= 5
    assert any(s["source_id"] == "sentinel-2-msi-l2a" for s in data["sources"])
    assert any(s["source_id"] == "quarantined-legacy-landsat-cache" for s in data["sources"])

    # Test filtering by lifecycle
    val_res = client.get("/evidence-registry?lifecycle=validated")
    assert val_res.status_code == 200
    val_data = val_res.json()
    assert all(s["lifecycle"] == "validated" for s in val_data["sources"])


def test_evidence_registry_single_source(client):
    res = client.get("/evidence-registry/sentinel-2-msi-l2a")
    assert res.status_code == 200
    data = res.json()
    assert data["source_id"] == "sentinel-2-msi-l2a"
    assert "e3b0c442" in data["content_hash"]
    assert data["is_operational_integration"] is True
    assert data["sutva_compliant"] is True


def test_structured_claims_endpoint(client):
    res = client.get("/claims/structured/kariba-redd")
    assert res.status_code == 200
    data = res.json()
    assert data["total_claims"] == 8
    assert data["supported_count"] >= 2
    assert data["partially_supported_count"] >= 3
    assert data["contradicted_count"] >= 2
    assert data["unverified_count"] >= 1

    # Check that individual claims have required and available evidence
    clm4 = next(c for c in data["claims"] if c["claim_id"] == "CLM-04-VEG")
    assert clm4["status"] == "CONTRADICTED"
    assert "Ridge-penalized Synthetic Control" in clm4["verification_methodology"]
    assert clm4["discrepancy_percentage"] < -50.0  # -73% overstatement


def test_groq_intelligence_endpoint(client):
    res = client.post(
        "/intelligence/research",
        json={
            "query": "Investigate additionality and leakage risk for Kariba REDD+",
            "mode": "csr_due_diligence",
            "project_id": "kariba-redd",
            "stakeholder_role": "csr",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["tokens_per_second"] > 100
    assert len(data["citations"]) >= 3
    assert len(data["contradictions"]) >= 2
    assert "GROQ LLM GUARDRAIL ACTIVE" in data["guardrail_notice"]


def test_benchmarks_endpoint(client):
    res = client.get("/benchmarks")
    assert res.status_code == 200
    data = res.json()
    assert data["total_cases"] == 5
    assert data["passed_cases"] == 5
    assert data["false_positive_rate"] == 0.0
    assert data["false_negative_rate"] == 0.0
    assert data["reproducibility_confirmed"] is True


def test_audit_ledger_and_reproducibility(client):
    res = client.get("/audit/ledger/kariba-redd")
    assert res.status_code == 200
    records = res.json()
    assert len(records) >= 1
    rec = records[0]
    assert rec["project_id"] == "kariba-redd"
    assert "merkle_root_hash" in rec

    # Verify reproducibility endpoint
    rep_res = client.post(
        "/audit/verify-reproducibility",
        json={
            "record_id": rec["record_id"],
            "recomputed_findings": {
                "point_estimate_att": 0.0241,
                "p_value": 0.0014,
                "discrepancy_vs_claimed": -73.0,
            },
        },
    )
    assert rep_res.status_code == 200
    assert rep_res.json()["reproducibility_verified"] is True
