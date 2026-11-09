"""Structured-claims routes are project-scoped, authenticated, and never leak Kariba data."""

from __future__ import annotations

import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parent))
from world import GRANTED_CASE, PRIVATE_CASE, World, build_world

from groundtruth.platform.store.models import OrganizationRow, ProjectRow

pytestmark = pytest.mark.usefixtures("_fast_scrypt")


@pytest.fixture
def world(client, sessions) -> World:
    return build_world(client, sessions)


def _new_project(world: World, org_name: str = "Outsider NGO", **over) -> str:
    """A freshly created project in an org: no boundary, no evidence, no claims."""
    with world.sessions() as db:
        org = db.execute(
            select(OrganizationRow).where(OrganizationRow.name == org_name)
        ).scalar_one()
        pid = str(uuid.uuid4())
        now = datetime.now(UTC)
        db.add(
            ProjectRow(
                id=pid,
                slug=over.get("slug", f"new-{pid[:8]}"),
                organization_id=org.id,
                case_id=None,
                name=over.get("name", "Brand New Project"),
                country="Kenya",
                ecosystem="mangrove",
                intervention="planting",
                treatment_start_year=2021,
                data_mode=over.get("data_mode", "observed"),
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()
    return pid


def test_new_project_without_evidence_gets_honest_empty_payload(world: World) -> None:
    pid = _new_project(world)
    r = world.client("outsider").get(f"/claims/structured/{pid}")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["total_claims"] == 0 and d["claims"] == []
    assert d["has_claims"] is False
    assert d["project_id"] == pid and d["project_name"] == "Brand New Project"
    assert d["overall_portfolio_grade"] == "N/A"
    assert d["is_demo"] is False and d["data_mode"] == "observed"
    ids = {m["id"] for m in d["missing_information"]}
    assert "claims_submitted" in ids and "boundary_verified" in ids
    assert all(m["action"] for m in d["missing_information"])
    assert d["next_steps"]
    assert d["supported_count"] == d["contradicted_count"] == d["unverified_count"] == 0


def test_no_kariba_leakage_for_non_kariba_project(world: World) -> None:
    pid = _new_project(world, slug="kariba", name="Another Project")  # slug imitates Kariba
    r = world.client("outsider").get(f"/claims/structured/{pid}")
    assert r.status_code == 200
    assert r.json()["claims"] == []
    for marker in ("784987", "Kariba", "CLM-04-VEG", "VCS-981"):
        assert marker not in r.text
    # the same slug through the by-slug path is also not Kariba data
    by_slug = world.client("outsider").get("/claims/structured/kariba")
    assert by_slug.status_code == 200 and by_slug.json()["claims"] == []


def test_kariba_demo_only_for_the_seeded_project_and_labelled_synthetic(world: World) -> None:
    pid = world.project_ids[GRANTED_CASE]
    r = world.client("ref").get(f"/claims/structured/{pid}")
    assert r.status_code == 200
    d = r.json()
    assert d["total_claims"] == 8
    assert d["data_mode"] == "synthetic" and d["is_demo"] is True
    assert "SIMULATED DATA" in d["notice"]
    assert d["project_id"] == pid  # the UUID, not a hardcoded slug


def test_cross_tenant_access_denied(world: World) -> None:
    private = world.project_ids[PRIVATE_CASE]
    fresh = _new_project(world)
    out = world.client("outsider")
    assert out.get(f"/claims/structured/{private}").status_code == 404
    # another org's brand-new project is equally invisible
    assert world.client("ref").get(f"/claims/structured/{fresh}").status_code == 404
    assert world.client("funder").get(f"/claims/structured/{fresh}").status_code == 404
    post = out.post("/claims/verify-structured", json={"project_id": private})
    assert post.status_code == 404


def test_unauthenticated_rejected(world: World, client) -> None:
    from authhelpers import new_client

    anon = new_client(client)
    pid = world.project_ids[GRANTED_CASE]
    assert anon.get(f"/claims/structured/{pid}").status_code == 401
    assert anon.get(f"/api/v1/claims/structured/{pid}").status_code == 401
    assert anon.post("/claims/verify-structured", json={"project_id": pid}).status_code == 401


def test_partial_evidence_custom_claims_are_unverified_not_graded_up(world: World) -> None:
    pid = _new_project(world)
    body = {
        "project_id": pid,
        "custom_claims": [
            {"claim_type": "area_restored", "claimed_value": 1200, "claimed_unit": "ha"},
            {
                "claim_type": "tree_survival",
                "claimed_value": 85,
                "claimed_unit": "percent",
                "available_evidence": ["Field survey report 2024"],
            },
        ],
    }
    r = world.client("outsider").post("/claims/verify-structured", json=body)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["total_claims"] == 2 and d["unverified_count"] == 2
    assert d["supported_count"] == 0
    c1, c2 = d["claims"]
    assert c1["available_evidence"] == [] and c1["missing_evidence"]
    assert c2["available_evidence"] == ["Field survey report 2024"]
    assert c1["grading"]["causal_confidence_score"] == 0.0
    assert "Kariba" not in r.text and "784987" not in r.text


def test_multiple_claims_get_sequential_ids(world: World) -> None:
    pid = _new_project(world)
    body = {"project_id": pid, "custom_claims": [{"claim_type": "area_restored"}] * 3}
    d = world.client("outsider").post("/claims/verify-structured", json=body).json()
    assert [c["claim_id"] for c in d["claims"]] == ["CLM-01", "CLM-02", "CLM-03"]


def test_invalid_claim_metadata_is_422_not_500(world: World) -> None:
    pid = _new_project(world)
    out = world.client("outsider")
    bad_type = out.post(
        "/claims/verify-structured",
        json={"project_id": pid, "custom_claims": [{"claim_type": "teleportation"}]},
    )
    assert bad_type.status_code == 422 and "claim_type" in bad_type.json()["detail"]
    bad_status = out.post(
        "/claims/verify-structured",
        json={"project_id": pid, "custom_claims": [{"claim_type": "area_restored", "status": "X"}]},
    )
    assert bad_status.status_code == 422
    not_obj = out.post(
        "/claims/verify-structured", json={"project_id": pid, "custom_claims": ["nope"]}
    )
    assert not_obj.status_code == 422
    default_pid = out.post("/claims/verify-structured", json={"custom_claims": []})
    assert default_pid.status_code in (404, 422)  # default id is not this org's project


def test_simulated_project_is_labelled_synthetic(world: World) -> None:
    pid = _new_project(world, data_mode="simulated")
    d = world.client("outsider").get(f"/claims/structured/{pid}").json()
    assert d["data_mode"] == "synthetic" and d["is_demo"] is False
