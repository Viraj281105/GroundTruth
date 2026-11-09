"""Ledger and report routes: real ledger state, report sealing, and tenant isolation."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parent))
from world import GRANTED_CASE, World

pytestmark = pytest.mark.usefixtures("_fast_scrypt")

KARIBA = GRANTED_CASE
EMPTY_SHA = hashlib.sha256(b"").hexdigest()


def _pid(world: World, who: str = "ref", slug: str = KARIBA) -> str:
    r = world.client(who).get(f"/projects/{slug}")
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_unauthenticated_requests_are_rejected(tenant_world: World, client) -> None:
    anon = tenant_world.client("ref").__class__(  # a fresh client with no session cookie
        tenant_world.client("ref").app, base_url=str(tenant_world.client("ref").base_url)
    )
    assert anon.get(f"/projects/{KARIBA}/ledger").status_code == 401
    assert anon.get("/orgs/reference/reports").status_code == 401
    assert anon.post(f"/projects/{KARIBA}/ledger/verify-reproducibility", json={}).status_code in (
        401,
        422,
    )


def test_the_old_global_ledger_routes_are_gone(tenant_world: World) -> None:
    for path in ("/audit/ledger/kariba-redd", "/api/v1/audit/ledger/kariba-redd"):
        assert tenant_world.client("ref").get(path).status_code == 404


def test_new_project_ledger_is_honestly_empty(tenant_world: World) -> None:
    pid = _pid(tenant_world)
    body = tenant_world.client("ref").get(f"/projects/{pid}/ledger").json()
    assert body["status"] == "empty"
    assert body["record_count"] == 0 and body["records"] == []
    assert body["ledger_root"] is None
    assert body["durable"] is True


def test_dossier_export_seals_the_exact_bytes(tenant_world: World) -> None:
    ref = tenant_world.client("ref")
    pid = _pid(tenant_world)
    r = ref.get(f"/projects/{KARIBA}/export/dossier")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    digest = "sha256:" + hashlib.sha256(r.content).hexdigest()
    assert r.headers["x-groundtruth-report-sha256"] == digest
    assert "x-groundtruth-ledger" not in r.headers  # i.e. not marked unsealed

    ledger = ref.get(f"/projects/{pid}/ledger").json()
    assert ledger["status"] == "verified" and ledger["record_count"] == 1
    rec = ledger["records"][0]
    assert rec["record_kind"] == "report.sealed"
    assert rec["record_id"] == r.headers["x-groundtruth-ledger-record"]
    assert rec["report_sha256"] == digest
    assert ledger["ledger_root"] == r.headers["x-groundtruth-ledger-root"]
    assert EMPTY_SHA not in ledger["ledger_root"] + rec["merkle_root_hash"]

    # the existing export contract is unchanged
    assert "attachment" in r.headers["content-disposition"]


def test_each_export_appends_to_one_verified_chain(tenant_world: World) -> None:
    ref = tenant_world.client("ref")
    pid = _pid(tenant_world)
    for _ in range(3):
        assert ref.get(f"/projects/{KARIBA}/export/dossier").status_code == 200
    ledger = ref.get(f"/projects/{pid}/ledger").json()
    assert ledger["status"] == "verified" and ledger["record_count"] == 3
    assert [x["sequence"] for x in ledger["records"]] == [1, 2, 3]


def test_verify_report_accepts_the_file_and_rejects_changes(tenant_world: World) -> None:
    ref = tenant_world.client("ref")
    pid = _pid(tenant_world)
    r = ref.get(f"/projects/{KARIBA}/export/dossier")
    rid = r.headers["x-groundtruth-ledger-record"]

    ok = ref.post(
        f"/projects/{pid}/ledger/verify-report",
        data={"record_id": rid},
        files={"file": ("d.zip", r.content, "application/zip")},
    ).json()
    assert ok["verified"] is True

    bad = ref.post(
        f"/projects/{pid}/ledger/verify-report",
        data={"record_id": rid},
        files={"file": ("d.zip", r.content + b"x", "application/zip")},
    ).json()
    assert bad["verified"] is False and "does not match" in bad["message"]


def test_tampering_is_surfaced_through_the_api(tenant_world: World) -> None:
    ref = tenant_world.client("ref")
    pid = _pid(tenant_world)
    ref.get(f"/projects/{KARIBA}/export/dossier")
    ref.get(f"/projects/{KARIBA}/export/dossier")
    with tenant_world.sessions() as db:
        db.execute(
            text("UPDATE audit_records SET git_commit_sha = 'forged' WHERE project_id = :p"),
            {"p": pid},
        )
        db.commit()
    assert ref.get(f"/projects/{pid}/ledger").json()["status"] == "failed"
    reports = ref.get("/orgs/reference/reports").json()["reports"]
    entry = next(e for e in reports if e["project_slug"] == KARIBA)
    assert entry["ledger"]["status"] == "failed"


def test_cross_tenant_ledger_access_is_denied(tenant_world: World) -> None:
    pid = _pid(tenant_world)
    tenant_world.client("ref").get(f"/projects/{KARIBA}/export/dossier")
    outsider = tenant_world.client("outsider")
    assert outsider.get(f"/projects/{pid}/ledger").status_code == 404
    assert outsider.get(f"/projects/{KARIBA}/ledger").status_code == 404
    assert outsider.get(f"/projects/{KARIBA}/export/dossier").status_code in (403, 404)


def test_verify_report_does_not_leak_records_of_other_projects(tenant_world: World) -> None:
    ref = tenant_world.client("ref")
    rid = ref.get(f"/projects/{KARIBA}/export/dossier").headers["x-groundtruth-ledger-record"]
    # the NGO has a grant on Kariba, so use a project it can read but that is not the record's
    other = _pid(tenant_world, "ref", "mikoko-pamoja")
    res = ref.post(
        f"/projects/{other}/ledger/verify-report",
        data={"record_id": rid},
        files={"file": ("d.zip", b"whatever", "application/zip")},
    ).json()
    assert res["verified"] is False and "No sealing record" in res["message"]


def test_reports_list_only_the_orgs_own_projects(tenant_world: World) -> None:
    outsider = tenant_world.client("outsider")
    assert outsider.get("/orgs/outsider-ngo/reports").json()["reports"] == []

    funder = tenant_world.client("funder").get(f"/orgs/{'demo-funder'}/reports").json()["reports"]
    kariba = next(e for e in funder if e["project_slug"] == KARIBA)
    assert kariba["access_level"] == "view"
    assert kariba["dossier_available"] is False and kariba["dossier_path"] is None
    assert kariba["last_sealed"] is None
    assert kariba["ledger"]["status"] == "empty"  # nothing sealed yet: never "sealed"

    auditor = tenant_world.client("auditor").get("/orgs/demo-auditor/reports").json()["reports"]
    entry = next(e for e in auditor if e["project_slug"] == KARIBA)
    assert entry["dossier_available"] is True and entry["dossier_path"].endswith("/export/dossier")


def test_reports_reflect_a_real_seal(tenant_world: World) -> None:
    auditor = tenant_world.client("auditor")
    r = auditor.get(f"/projects/{KARIBA}/export/dossier")
    assert r.status_code == 200
    entry = next(
        e
        for e in auditor.get("/orgs/demo-auditor/reports").json()["reports"]
        if e["project_slug"] == KARIBA
    )
    assert entry["ledger"]["status"] == "verified"
    assert entry["last_sealed"]["record_id"] == r.headers["x-groundtruth-ledger-record"]
    assert entry["last_sealed"]["report_sha256"] == r.headers["x-groundtruth-report-sha256"]
    assert entry["last_sealed"]["size_bytes"] == len(r.content)


def test_reproducibility_is_scoped_and_compares_real_findings(tenant_world: World) -> None:
    ref = tenant_world.client("ref")
    pid = _pid(tenant_world)
    from groundtruth.platform.audit.ledger import AuditLedger

    rec = AuditLedger(tenant_world.sessions).record_assessment(
        pid, {"type": "Point", "coordinates": [0, 0]}, {"seed": 1}, {"att": 0.5}
    )
    same = ref.post(
        f"/projects/{pid}/ledger/verify-reproducibility",
        json={"record_id": rec.record_id, "recomputed_findings": {"att": 0.5}},
    ).json()
    assert same["reproducibility_verified"] is True
    diff = ref.post(
        f"/projects/{pid}/ledger/verify-reproducibility",
        json={"record_id": rec.record_id, "recomputed_findings": {"att": 0.6}},
    ).json()
    assert diff["reproducibility_verified"] is False
    other = _pid(tenant_world, "ref", "mikoko-pamoja")
    cross = ref.post(
        f"/projects/{other}/ledger/verify-reproducibility",
        json={"record_id": rec.record_id, "recomputed_findings": {"att": 0.5}},
    ).json()
    assert cross["reproducibility_verified"] is False
