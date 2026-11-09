"""Promoting extracted statements to project claims, and matching them against evidence."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_observation_ingestion import SQUARE, fake_provider
from world import GRANTED_CASE, World

from groundtruth.platform.config import get_settings
from groundtruth.platform.projects import ingestion
from groundtruth.platform.store.models import AuditEventRow, ProjectClaimRow

pytestmark = pytest.mark.usefixtures("_fast_scrypt")

# The square boundary is 0.1 x 0.1 degrees near the equator: about 12,300 hectares.
TEXT = (
    "The project covers 12,000 hectares of degraded miombo woodland. "
    "85% of planted seedlings survived after 3 years. "
    "NDVI increased by 0.05 since 2021. "
    "The project has sequestered 40,000 tCO2e and proves biodiversity has fully recovered."
)


@pytest.fixture(autouse=True)
def _isolated_dirs(tmp_path, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "cases_dir", tmp_path / "cases")
    monkeypatch.setattr(s, "data_dir", tmp_path / "data")
    monkeypatch.setattr(s, "project_documents_dir", tmp_path / "docs")
    monkeypatch.setattr(s, "observation_ingestion_enabled", True)


def _project(world: World) -> str:
    r = world.client("outsider").post(
        "/orgs/outsider-ngo/projects",
        data={
            "name": "Riverbank",
            "country": "Zambia",
            "ecosystem": "miombo",
            "intervention": "reforestation",
            "treatment_start_year": "2019",
        },
        files={"boundary": ("b.geojson", json.dumps(SQUARE).encode())},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _upload(world: World, pid: str, text: str = TEXT, name: str = "claims.txt") -> str:
    r = world.client("outsider").post(
        f"/projects/{pid}/documents", files={"file": (name, text.encode(), "text/plain")}
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _candidates(world: World, pid: str, doc: str) -> dict[str, dict[str, Any]]:
    r = world.client("outsider").get(f"/projects/{pid}/documents/{doc}/extraction")
    assert r.status_code == 200, r.text
    return {c["kind"]: c for c in r.json()["candidates"]}


def _promote(world: World, pid: str, doc: str, cand: dict[str, Any], **over: Any):
    body = {"document_id": doc, "start": cand["start"], "end": cand["end"], **over}
    return world.client("outsider").post(f"/projects/{pid}/claims", json=body)


def _ingest(world: World, pid: str, ndvi_nir: dict[int, float]) -> None:
    r = world.client("outsider").post(
        f"/projects/{pid}/observations/ingestions",
        json={"start_year": 2021, "end_year": 2023, "indicators": ["ndvi"]},
    )
    assert r.status_code == 202, r.text
    ingestion.process_pending(world.sessions, "w", limit=1, ingest_fn=fake_provider(ndvi_nir))


def _claims(world: World, pid: str) -> list[dict[str, Any]]:
    return world.client("outsider").get(f"/projects/{pid}/claims").json()["claims"]


# --- nothing is promoted automatically -------------------------------------------------------------


def test_uploading_a_document_creates_candidates_but_never_claims(tenant_world: World) -> None:
    pid = _project(tenant_world)
    doc = _upload(tenant_world, pid)
    assert len(_candidates(tenant_world, pid, doc)) >= 4
    assert _claims(tenant_world, pid) == []
    portfolio = tenant_world.client("outsider").get(f"/claims/structured/{pid}").json()
    assert portfolio["total_claims"] == 0 and portfolio["has_claims"] is False
    assert any(m["id"] == "claims_submitted" for m in portfolio["missing_information"])


def test_candidates_carry_what_the_reviewer_needs(tenant_world: World) -> None:
    pid = _project(tenant_world)
    cands = _candidates(tenant_world, pid, _upload(tenant_world, pid))
    over = cands["biodiversity_recovery"]
    assert over["status"] == "overclaim" and over["reason"] and over["evidence_gap"]
    assert cands["vegetation_index_change"]["period"] == "since 2021"


# --- promotion preserves the source ---------------------------------------------------------------


def test_promotion_stores_exactly_what_the_document_said(tenant_world: World) -> None:
    pid = _project(tenant_world)
    doc = _upload(tenant_world, pid)
    cand = _candidates(tenant_world, pid, doc)["area_hectares"]
    r = _promote(tenant_world, pid, doc, cand)
    assert r.status_code == 201, r.text
    src = r.json()["source"]
    assert src["original_text"] == TEXT[cand["start"] : cand["end"]]
    assert src["document_id"] == doc and src["document_name"] == "claims.txt"
    assert src["document_sha256"] and src["edited"] is False
    assert (src["kind"], src["value"], src["unit"]) == ("area_hectares", 12000.0, "ha")
    assert r.json()["outcome"]["status"] == "SUPPORTED"  # 12,000 ha vs ~12,300 ha boundary


def test_a_correction_changes_what_is_tested_not_what_was_read(tenant_world: World) -> None:
    pid = _project(tenant_world)
    doc = _upload(tenant_world, pid)
    cand = _candidates(tenant_world, pid, doc)["area_hectares"]
    r = _promote(tenant_world, pid, doc, cand, value=2000)  # reviewer says the extractor misread it
    src = r.json()["source"]
    assert src["value"] == 2000 and src["original_value"] == 12000.0 and src["edited"] is True
    assert r.json()["outcome"]["status"] == "PARTIALLY_SUPPORTED"  # fits inside, extent not shown

    cid = r.json()["id"]
    p = tenant_world.client("outsider").patch(
        f"/projects/{pid}/claims/{cid}",
        json={"value": 30000, "statement_text": "The project covers 30,000 hectares."},
    )
    assert p.status_code == 200
    body = p.json()
    assert body["outcome"]["status"] == "CONTRADICTED"  # larger than the boundary
    assert body["source"]["original_text"] == TEXT[cand["start"] : cand["end"]]  # never changes
    assert body["source"]["original_value"] == 12000.0 and body["source"]["edited"] is True

    # an edit that restores the original values is no longer an edit of the numbers
    back = tenant_world.client("outsider").patch(
        f"/projects/{pid}/claims/{cid}",
        json={"value": 12000, "statement_text": TEXT[cand["start"] : cand["end"]]},
    )
    assert back.json()["source"]["edited"] is False


def test_a_typed_claim_has_no_document_source(tenant_world: World) -> None:
    pid = _project(tenant_world)
    r = tenant_world.client("outsider").post(
        f"/projects/{pid}/claims",
        json={
            "statement_text": "We restored 500 hectares",
            "kind": "area_hectares",
            "value": 500,
            "unit": "ha",
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["source"]["document_id"] is None
    assert r.json()["source"]["original_text"] == "We restored 500 hectares"
    assert r.json()["outcome"]["status"] == "PARTIALLY_SUPPORTED"


@pytest.mark.parametrize(
    ("body", "status", "code"),
    [
        ({"statement_text": "x"}, 422, "invalid_claim"),  # too short
        ({"statement_text": "We restored land", "kind": "banana"}, 422, "invalid_claim"),
        ({"statement_text": "We restored land"}, 422, "invalid_claim"),  # typed claims need a kind
        ({"document_id": "no-such", "start": 0, "end": 5}, 404, "document_not_found"),
        ({"document_id": "x", "start": 5, "end": 2}, 422, "invalid_claim"),
    ],
)
def test_invalid_promotions_are_rejected_with_a_reason(
    tenant_world: World, body, status, code
) -> None:
    pid = _project(tenant_world)
    r = tenant_world.client("outsider").post(f"/projects/{pid}/claims", json=body)
    assert r.status_code == status, r.text
    assert r.json()["detail"]["code"] == code


def test_a_span_that_is_not_an_extracted_statement_is_refused(tenant_world: World) -> None:
    pid = _project(tenant_world)
    doc = _upload(tenant_world, pid)
    r = tenant_world.client("outsider").post(
        f"/projects/{pid}/claims", json={"document_id": doc, "start": 3, "end": 40}
    )
    assert r.status_code == 409 and r.json()["detail"]["code"] == "source_not_found"


def test_the_same_statement_cannot_be_promoted_twice(tenant_world: World) -> None:
    pid = _project(tenant_world)
    doc = _upload(tenant_world, pid)
    cand = _candidates(tenant_world, pid, doc)["area_hectares"]
    assert _promote(tenant_world, pid, doc, cand).status_code == 201
    again = _promote(tenant_world, pid, doc, cand)
    assert again.status_code == 409 and again.json()["detail"]["code"] == "already_promoted"


def test_an_unreadable_document_cannot_be_a_source(tenant_world: World) -> None:
    pid = _project(tenant_world)
    pdf = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
    r = tenant_world.client("outsider").post(
        f"/projects/{pid}/documents", files={"file": ("a.pdf", pdf, "application/pdf")}
    )
    doc = r.json()["id"]
    res = tenant_world.client("outsider").post(
        f"/projects/{pid}/claims", json={"document_id": doc, "start": 0, "end": 10}
    )
    assert res.status_code == 409 and res.json()["detail"]["code"] == "document_not_readable"


# --- matching against evidence ----------------------------------------------------------------------------


def test_every_kind_of_extracted_statement_gets_an_honest_outcome(tenant_world: World) -> None:
    pid = _project(tenant_world)
    doc = _upload(tenant_world, pid)
    for cand in _candidates(tenant_world, pid, doc).values():
        assert _promote(tenant_world, pid, doc, cand).status_code == 201
    by_kind = {c["source"]["kind"]: c for c in _claims(tenant_world, pid)}
    # nothing satellite greenness can establish is ever supported, however much data exists
    for kind in ("survival_rate", "carbon_tco2e", "biodiversity_recovery"):
        out = by_kind[kind]["outcome"]
        assert out["status"] == "UNVERIFIED" and out["reasons"] and out["missing_evidence"], kind
        assert by_kind[kind]["checkable"] is False
    assert by_kind["area_hectares"]["checkable"] is True
    # no observations yet: the greenness claim cannot be tested, and says what to do
    veg = by_kind["vegetation_index_change"]["outcome"]
    assert veg["status"] == "UNVERIFIED"
    assert any("Earth observation tab" in m for m in veg["missing_evidence"])


def test_ingested_observations_change_the_outcome_of_the_greenness_claim(
    tenant_world: World,
) -> None:
    pid = _project(tenant_world)
    doc = _upload(tenant_world, pid)
    cand = _candidates(tenant_world, pid, doc)["vegetation_index_change"]
    cid = _promote(tenant_world, pid, doc, cand).json()["id"]
    assert _claims(tenant_world, pid)[0]["outcome"]["status"] == "UNVERIFIED"

    # NDVI = (NIR - 2000) / (NIR + 2000): 2021 -> 0.500, 2023 -> 0.556; observed change +0.056
    _ingest(tenant_world, pid, {2021: 6000, 2022: 6300, 2023: 7000})
    out = _claims(tenant_world, pid)[0]["outcome"]
    assert out["status"] == "SUPPORTED", out["headline"]
    assert out["observed_value"] == pytest.approx(0.0556, abs=1e-3)
    assert any("caused it" in lim for lim in out["limitations"])

    tenant_world.client("outsider").patch(f"/projects/{pid}/claims/{cid}", json={"value": 0.5})
    assert _claims(tenant_world, pid)[0]["outcome"]["status"] == "CONTRADICTED"


def test_promoted_claims_appear_in_the_verification_workbench_payload(tenant_world: World) -> None:
    pid = _project(tenant_world)
    doc = _upload(tenant_world, pid)
    cands = _candidates(tenant_world, pid, doc)
    for kind in ("area_hectares", "survival_rate"):
        _promote(tenant_world, pid, doc, cands[kind])
    p = tenant_world.client("outsider").get(f"/claims/structured/{pid}").json()
    assert p["total_claims"] == 2 and p["has_claims"] is True
    assert p["supported_count"] == 1 and p["unverified_count"] == 1
    assert p["is_demo"] is False and p["data_mode"] == "observed"
    assert not any(m["id"] == "claims_submitted" for m in p["missing_information"])
    area = next(c for c in p["claims"] if c["claim_type"] == "area_restored")
    assert (
        area["source"]["original_text"]
        == TEXT[cands["area_hectares"]["start"] : cands["area_hectares"]["end"]]
    )
    assert area["headline"] and area["reasons"]
    assert "Kariba" not in json.dumps(p)


# --- withdrawal, permissions, isolation, audit ------------------------------------------------------------


def test_withdrawing_hides_a_claim_but_keeps_the_record(tenant_world: World) -> None:
    pid = _project(tenant_world)
    doc = _upload(tenant_world, pid)
    cid = _promote(
        tenant_world, pid, doc, _candidates(tenant_world, pid, doc)["area_hectares"]
    ).json()["id"]
    c = tenant_world.client("outsider")
    assert c.delete(f"/projects/{pid}/claims/{cid}").status_code == 204
    assert _claims(tenant_world, pid) == []
    assert c.get(f"/claims/structured/{pid}").json()["total_claims"] == 0
    assert c.delete(f"/projects/{pid}/claims/{cid}").status_code == 404
    assert c.patch(f"/projects/{pid}/claims/{cid}", json={"value": 1}).status_code in (404, 409)
    with tenant_world.sessions() as db:
        row = db.execute(select(ProjectClaimRow)).scalars().one()
        assert row.withdrawn_at is not None and row.original_text  # history retained
    # a withdrawn statement can be promoted again
    assert (
        _promote(
            tenant_world, pid, doc, _candidates(tenant_world, pid, doc)["area_hectares"]
        ).status_code
        == 201
    )


def test_permissions_and_tenant_isolation(tenant_world: World) -> None:
    pid = _project(tenant_world)
    doc = _upload(tenant_world, pid)
    cand = _candidates(tenant_world, pid, doc)["area_hectares"]
    cid = _promote(tenant_world, pid, doc, cand).json()["id"]
    base = f"/projects/{pid}/claims"

    other = tenant_world.client("ngo")  # a different organization
    assert other.get(base).status_code == 404
    assert (
        other.post(
            base, json={"statement_text": "We restored land", "kind": "area_hectares"}
        ).status_code
        == 404
    )
    assert other.patch(f"{base}/{cid}", json={"value": 1}).status_code == 404
    assert other.delete(f"{base}/{cid}").status_code == 404

    # a view-level grantee reads outcomes but cannot add, edit or withdraw
    k = f"/projects/{GRANTED_CASE}/claims"
    f = tenant_world.client("funder")
    assert f.get(k).status_code == 200
    assert (
        f.post(k, json={"statement_text": "We restored land", "kind": "area_hectares"}).status_code
        == 403
    )
    anon = tenant_world.client("outsider").__class__(
        tenant_world.client("outsider").app, base_url=str(tenant_world.client("outsider").base_url)
    )
    assert anon.get(base).status_code == 401


def test_a_claim_of_another_project_is_invisible(tenant_world: World) -> None:
    a, b = _project(tenant_world), _project(tenant_world)
    doc = _upload(tenant_world, a)
    cid = _promote(tenant_world, a, doc, _candidates(tenant_world, a, doc)["area_hectares"]).json()[
        "id"
    ]
    c = tenant_world.client("outsider")
    assert c.patch(f"/projects/{b}/claims/{cid}", json={"value": 1}).status_code == 404
    assert c.delete(f"/projects/{b}/claims/{cid}").status_code == 404
    assert _claims(tenant_world, b) == []


def test_promote_edit_and_withdraw_are_audited(tenant_world: World) -> None:
    pid = _project(tenant_world)
    doc = _upload(tenant_world, pid)
    cid = _promote(
        tenant_world, pid, doc, _candidates(tenant_world, pid, doc)["area_hectares"]
    ).json()["id"]
    c = tenant_world.client("outsider")
    c.patch(f"/projects/{pid}/claims/{cid}", json={"value": 100})
    c.delete(f"/projects/{pid}/claims/{cid}")
    with tenant_world.sessions() as db:
        actions = [e.action for e in db.execute(select(AuditEventRow)).scalars()]
    assert {"claim.promote", "claim.edit", "claim.withdraw"} <= set(actions)
