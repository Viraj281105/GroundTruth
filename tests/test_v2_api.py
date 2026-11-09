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
    # No source has a validated automated ingestion path; counts must stay truthful.
    assert data["operational_count"] == 0
    assert data["blocked_count"] >= 6
    assert any(s["source_id"] == "sentinel-2-msi-l2a" for s in data["sources"])
    assert any(s["source_id"] == "quarantined-legacy-landsat-cache" for s in data["sources"])

    # Test filtering by lifecycle
    val_res = client.get("/evidence-registry?lifecycle=integrated")
    assert val_res.status_code == 200
    val_data = val_res.json()
    assert val_data["sources"]
    assert all(s["lifecycle"] == "integrated" for s in val_data["sources"])
    assert client.get("/evidence-registry?lifecycle=validated").json()["sources"] == []
    assert client.get("/evidence-registry?operational_only=true").json()["sources"] == []


def test_evidence_registry_single_source(client):
    res = client.get("/evidence-registry/sentinel-2-msi-l2a")
    assert res.status_code == 200
    data = res.json()
    assert data["source_id"] == "sentinel-2-msi-l2a"
    assert data["is_operational_integration"] is False
    assert data["ingestion_mode"] == "accessible_unvalidated"
    assert data["blocked_for_production_analysis"] is True
    # Hash, if present, is a real sha256 of the named local artefact (never a placeholder).
    assert data["content_hash"] is None or data["content_hash"].startswith("sha256:")


def test_structured_claims_endpoint_requires_a_session(client):
    # Project-scoped and authenticated since WP-B; the tenancy suite covers the allowed paths.
    res = client.get("/claims/structured/kariba-redd")
    assert res.status_code in (401, 404)


def test_kariba_demo_portfolio_engine():
    from groundtruth.claims import verify_project_claims

    data = verify_project_claims(project_id="kariba-redd").to_dict()
    assert data["total_claims"] == 8
    assert data["data_mode"] == "synthetic" and data["is_demo"] is True
    assert data["supported_count"] >= 2
    assert data["partially_supported_count"] >= 3
    assert data["contradicted_count"] >= 2
    assert data["unverified_count"] >= 1
    clm4 = next(c for c in data["claims"] if c["claim_id"] == "CLM-04-VEG")
    assert clm4["status"] == "CONTRADICTED"
    assert "Ridge-penalized Synthetic Control" in clm4["verification_methodology"]
    assert clm4["discrepancy_percentage"] < -50.0  # -73% overstatement


def test_unknown_project_never_gets_kariba_claims():
    from groundtruth.claims import verify_project_claims

    data = verify_project_claims(project_id="some-new-project").to_dict()
    assert data["total_claims"] == 0 and data["claims"] == []
    assert data["is_demo"] is False


def test_claims_analyze_returns_all_statements_and_unrecognised(client):
    text = (
        "The project restores 1,200 hectares of degraded dry forest. "
        "85% of planted seedlings survived after 3 years. NDVI increased by 0.15 since 2021. "
        "The project has sequestered 40,000 tCO2e and proves biodiversity has fully recovered. "
        "Meetings were held."
    )
    res = client.post("/claims/analyze", json={"text": text})
    assert res.status_code == 200, res.text
    d = res.json()
    assert [s["kind"] for s in d["statements"]] == [
        "area_hectares",
        "survival_rate",
        "vegetation_index_change",
        "carbon_tco2e",
        "biodiversity_recovery",
    ]
    for s in d["statements"]:
        assert text[s["span"]["start"] : s["span"]["end"]] == s["text"]
        assert s["reason"] and s["evidence_gap"]
    assert [u["text"] for u in d["unrecognised_sentences"]] == ["Meetings were held"]
    assert d["claims"]  # legacy field unchanged
    assert d["comparisons"] == []


def test_groq_intelligence_endpoint_requires_sign_in(client):
    """Project-scoped and authenticated; behaviour is covered in tests/tenancy/test_intelligence_api.py."""
    res = client.post(
        "/intelligence/research",
        json={"query": "Investigate additionality and leakage", "project_id": "any"},
    )
    assert res.status_code == 401


def test_benchmarks_endpoint_requires_sign_in(client):
    """The suite is compute-heavy, so it is no longer open to anonymous callers."""
    assert client.get("/benchmarks").status_code == 401
    assert client.get("/api/v1/benchmarks").status_code == 401


def test_benchmark_suite_itself_still_runs():
    from groundtruth.engine.benchmark.suite import run_independent_benchmark_suite

    data = run_independent_benchmark_suite().to_dict()
    assert data["total_cases"] == 5
    assert data["passed_cases"] == 5
    assert data["reproducibility_confirmed"] is True


# The former global ``/audit/ledger`` test was removed: it asserted a Kariba record invented
# for any project id. Ledger behaviour is covered by tests/test_audit_persistence.py and
# tests/tenancy/test_ledger_api.py.
