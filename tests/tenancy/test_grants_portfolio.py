"""Task 10: project grants, the portfolio, the activity feed, the audit-log API, the dossier."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select, update

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "auth"))
from authhelpers import ORIGIN, PASSWORD, login, new_client, register
from world import GRANTED_CASE, PRIVATE_CASE, World

from groundtruth.platform.audit.service import record_event
from groundtruth.platform.store.models import AuditEventRow, ProjectGrantRow, ProjectRow

pytestmark = pytest.mark.usefixtures("_fast_scrypt")

KARIBA = GRANTED_CASE
MIKOKO = PRIVATE_CASE  # seeded simulated, no grant to anyone
FUNDER = "demo-funder"


def _grant(world: World, project: str, org: str, level: str = "view"):
    return world.client("ref").post(
        f"/projects/{project}/grants", json={"org_slug": org, "level": level}
    )


def _add_member(world: World, email: str, role: str, owner: str = "ref", org: str = "reference"):
    """Register ``email`` and add it to ``org`` (via ``owner``'s client) with ``role``."""
    c = new_client(world.client("ref"))
    c.headers["Origin"] = ORIGIN
    assert register(c, email).status_code in (200, 201)
    r = world.client(owner).post(f"/orgs/{org}/members", json={"email": email, "role": role})
    assert r.status_code == 201, r.text
    assert login(c, email, PASSWORD).status_code == 200
    return c


# --- grants ------------------------------------------------------------------------------------


def test_grant_then_visible(tenant_world: World) -> None:
    funder = tenant_world.client("funder")
    assert funder.get(f"/projects/{MIKOKO}").status_code == 404
    r = _grant(tenant_world, MIKOKO, FUNDER, "view")
    assert r.status_code == 201, r.text
    assert r.json()["org_slug"] == FUNDER and r.json()["level"] == "view"
    assert funder.get(f"/projects/{MIKOKO}").json()["access_level"] == "view"
    listing = tenant_world.client("ref").get(f"/projects/{MIKOKO}/grants")
    assert [(g["org_slug"], g["level"]) for g in listing.json()] == [(FUNDER, "view")]


def test_revoked_grant_hides_project(tenant_world: World) -> None:
    funder = tenant_world.client("funder")
    ref = tenant_world.client("ref")
    assert _grant(tenant_world, MIKOKO, FUNDER).status_code == 201
    assert funder.get(f"/projects/{MIKOKO}").status_code == 200
    assert ref.delete(f"/projects/{MIKOKO}/grants/{FUNDER}").status_code == 204
    assert funder.get(f"/projects/{MIKOKO}").status_code == 404
    assert ref.get(f"/projects/{MIKOKO}/grants").json() == []
    with tenant_world.sessions() as db:  # the row stays for the audit trail
        rows = list(db.execute(select(ProjectGrantRow)).scalars())
        assert any(g.revoked_at is not None for g in rows)
    # re-granting after revoke reactivates (and may change the level)
    assert _grant(tenant_world, MIKOKO, FUNDER, "audit").status_code == 201
    assert funder.get(f"/projects/{MIKOKO}").json()["access_level"] == "audit"


def test_grant_rules(tenant_world: World) -> None:
    ref = tenant_world.client("ref")
    assert _grant(tenant_world, MIKOKO, "reference").status_code == 422
    unknown = _grant(tenant_world, MIKOKO, "no-such-org")
    assert unknown.status_code == 404
    assert unknown.json()["detail"]["message"] == "Organization not found."
    assert _grant(tenant_world, MIKOKO, FUNDER, "owner").status_code == 422
    assert ref.delete(f"/projects/{MIKOKO}/grants/{FUNDER}").status_code == 404  # no active grant


def test_only_the_owning_org_manages_grants(tenant_world: World) -> None:
    ngo = tenant_world.client("ngo")  # contribute on Kariba
    assert ngo.get(f"/projects/{KARIBA}/grants").status_code == 403
    r = ngo.post(f"/projects/{KARIBA}/grants", json={"org_slug": FUNDER, "level": "view"})
    assert r.status_code == 403
    assert ngo.delete(f"/projects/{KARIBA}/grants/{FUNDER}").status_code == 403
    out = tenant_world.client("outsider")
    assert out.get(f"/projects/{KARIBA}/grants").status_code == 404
    assert out.get(f"/projects/{MIKOKO}/grants").status_code == 404
    viewer = _add_member(tenant_world, "viewer1@example.org", "viewer")
    assert viewer.get(f"/projects/{KARIBA}/grants").status_code == 403  # role


def test_grant_and_revoke_are_audited(tenant_world: World) -> None:
    _grant(tenant_world, MIKOKO, FUNDER, "audit")
    tenant_world.client("ref").delete(f"/projects/{MIKOKO}/grants/{FUNDER}")
    with tenant_world.sessions() as db:
        rows = list(
            db.execute(
                select(AuditEventRow)
                .where(AuditEventRow.action.in_(["project.grant", "project.revoke"]))
                .order_by(AuditEventRow.occurred_at)
            ).scalars()
        )
    assert [r.action for r in rows] == ["project.grant", "project.revoke"]
    assert rows[0].details == {"grantee": FUNDER, "level": "audit"}
    assert rows[1].details == {"grantee": FUNDER, "level": "audit"}
    assert rows[0].resource_type == "project"


# --- portfolio ---------------------------------------------------------------------------------


def _by_slug(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {r["project"]["slug"]: r for r in rows}


def test_portfolio_rows_and_redaction(tenant_world: World) -> None:
    r = tenant_world.client("funder").get(f"/orgs/{FUNDER}/portfolio")
    assert r.status_code == 200, r.text
    body = r.json()
    rows = _by_slug(body["projects"])
    assert set(rows) == {KARIBA}
    row = rows[KARIBA]
    assert row["access_level"] == "view"
    assert set(row["dimension_statuses"]) == {"trajectory", "risk", "evidence_quality"}
    assert 0 <= row["assessment_level"] <= 5 and row["level_name"]
    assert row["data_mode"] == "observed" and row["reported_funding"] is None
    assert row["attribution_verdict"] in {"Supported", "Not supported", "Inconclusive"}
    rec = row["top_recommendation"]
    assert rec is None or ("diagnostic_refs" not in rec and "funder" in rec["personas"])
    assert all(p["data_mode"] == "simulated" for p in body["simulated"])
    # consistent with the project assessment endpoint (never recomputed differently)
    a = tenant_world.client("funder").get(f"/projects/{KARIBA}/assessment").json()
    assert (row["assessment_level"], row["level_name"]) == (a["level"], a["level_name"])
    assert row["evidence_confidence"] == a["evidence_confidence"]
    assert row["attribution_verdict"] == a["attribution"]["verdict"]


def test_portfolio_keeps_simulated_apart(tenant_world: World) -> None:
    assert _grant(tenant_world, MIKOKO, FUNDER).status_code == 201
    body = tenant_world.client("funder").get(f"/orgs/{FUNDER}/portfolio").json()
    assert {r["project"]["slug"] for r in body["projects"]} == {KARIBA}
    assert MIKOKO in {r["project"]["slug"] for r in body["simulated"]}
    assert all(r["data_mode"] == "simulated" for r in body["simulated"])
    assert "total" not in json.dumps(body).lower()
    ref = tenant_world.client("ref").get("/orgs/reference/portfolio").json()
    assert all(r["access_level"] == "owner" for r in ref["projects"] + ref["simulated"])
    order = [(-r["assessment_level"], r["project"]["name"]) for r in ref["projects"]]
    assert order == sorted(order)


def test_portfolio_never_computes_funding(tenant_world: World) -> None:
    ref = tenant_world.client("ref")
    rows = ref.get("/orgs/reference/portfolio").json()
    assert all(r["reported_funding"] is None for r in rows["projects"] + rows["simulated"])
    with tenant_world.sessions() as db:
        db.execute(
            update(ProjectRow)
            .where(ProjectRow.slug == KARIBA)
            .values(reported_funding_amount=1250000.5, reported_funding_currency="USD")
        )
        db.commit()
    for who, slug in (("ref", "reference"), ("funder", FUNDER)):
        got = _by_slug(tenant_world.client(who).get(f"/orgs/{slug}/portfolio").json()["projects"])
        assert got[KARIBA]["reported_funding"] == {
            "amount": 1250000.5,
            "currency": "USD",
            "reported_by": "GroundTruth Reference",
        }
    other = ref.get("/orgs/reference/portfolio").json()["simulated"]
    assert all(r["reported_funding"] is None for r in other)


def test_portfolio_is_scoped_to_the_active_org(tenant_world: World) -> None:
    assert tenant_world.client("funder").get("/orgs/reference/portfolio").status_code == 404
    assert tenant_world.client("outsider").get("/orgs/outsider-ngo/portfolio").json() == {
        "projects": [],
        "simulated": [],
    }


# --- audit + activity --------------------------------------------------------------------------


def test_audit_log_admin_only(tenant_world: World) -> None:
    ref = tenant_world.client("ref")
    _grant(tenant_world, MIKOKO, FUNDER)
    ref.delete(f"/projects/{MIKOKO}/grants/{FUNDER}")
    _grant(tenant_world, MIKOKO, FUNDER)
    page = ref.get("/orgs/reference/audit?limit=2")
    assert page.status_code == 200
    body = page.json()
    assert len(body["events"]) == 2 and body["next_cursor"]
    assert {"id", "occurred_at", "action", "outcome", "ip", "details"} <= set(body["events"][0])
    nxt = ref.get(f"/orgs/reference/audit?limit=2&cursor={body['next_cursor']}").json()
    assert {e["id"] for e in nxt["events"]}.isdisjoint({e["id"] for e in body["events"]})
    assert ref.get("/orgs/reference/audit?cursor=garbage").status_code == 422
    admin = _add_member(tenant_world, "admin1@example.org", "admin")
    assert admin.get("/orgs/reference/audit").status_code == 200
    for role in ("member", "viewer"):
        c = _add_member(tenant_world, f"{role}2@example.org", role)
        assert c.get("/orgs/reference/audit").status_code == 403


def test_audit_log_names_member_actors_and_hides_outsiders(tenant_world: World) -> None:
    ref = tenant_world.client("ref")
    _grant(tenant_world, MIKOKO, FUNDER)
    events = ref.get("/orgs/reference/audit?limit=200").json()["events"]
    grants = [e for e in events if e["action"] == "project.grant"]
    assert grants and all(e["actor_email"] for e in grants)
    assert all(e["actor_user_id"] for e in grants)
    # An actor who is not a member of the viewing organization stays anonymous (id only).
    with tenant_world.sessions() as db:
        outsider_id = tenant_world.user_ids["outsider"]
        record_event(
            db,
            action="org.switch",
            outcome="success",
            actor_user_id=outsider_id,
            organization_id=tenant_world.org_ids["reference"],
            resource_type="organization",
        )
        db.commit()
    events = ref.get("/orgs/reference/audit?limit=200").json()["events"]
    foreign = [e for e in events if e["actor_user_id"] == outsider_id]
    assert foreign and all(e["actor_email"] is None for e in foreign)


def test_activity_excludes_auth_and_membership_events(tenant_world: World) -> None:
    _grant(tenant_world, MIKOKO, FUNDER)
    viewer = _add_member(tenant_world, "viewer3@example.org", "viewer")
    r = viewer.get("/orgs/reference/activity?limit=20")
    assert r.status_code == 200, r.text
    items = r.json()
    assert items, "the grant should appear"
    for item in items:
        assert item["action"].startswith(("project.", "run.", "export."))
        assert not {"ip", "user_agent", "actor_user_id", "details"} & set(item)
    assert "project.grant" in {i["action"] for i in items}
    with tenant_world.sessions() as db:  # the org log does hold org.* events the feed hides
        found = db.execute(
            select(AuditEventRow).where(AuditEventRow.action == "org.member_add")
        ).first()
        assert found is not None
    assert viewer.get("/orgs/reference/activity?limit=0").status_code == 422


def test_activity_hides_other_orgs_events_and_revoked_projects(tenant_world: World) -> None:
    funder = tenant_world.client("funder")
    auditor = tenant_world.client("auditor")
    assert auditor.get(f"/projects/{KARIBA}/export/dossier").status_code == 200
    assert funder.get(f"/orgs/{FUNDER}/activity").json() == []  # the auditor's export is not ours
    ref_items = tenant_world.client("ref").get("/orgs/reference/activity").json()
    assert "export.download" in {i["action"] for i in ref_items}  # the owner sees it
    assert auditor.get("/orgs/demo-auditor/activity").json() != []
    tenant_world.client("ref").delete(f"/projects/{KARIBA}/grants/demo-auditor")
    assert auditor.get("/orgs/demo-auditor/activity").json() == []


# --- dossier -----------------------------------------------------------------------------------

FILES = [
    "README.md",
    "assessment.json",
    "climate.csv",
    "evidence-inventory.json",
    "observations.csv",
    "provenance.json",
    "readiness.json",
    "manifest.json",
]


def _zip(content: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        return {n: z.read(n) for n in z.namelist()}


def test_dossier_manifest_hashes_match(tenant_world: World) -> None:
    r = tenant_world.client("auditor").get(f"/projects/{KARIBA}/export/dossier")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    assert "attachment" in r.headers["content-disposition"]
    files = _zip(r.content)
    assert list(files) == FILES  # sorted names, manifest last
    manifest = json.loads(files["manifest.json"])
    listed = [e["path"] for e in manifest["files"]]
    assert listed == [n for n in FILES if n != "manifest.json"]
    for entry in manifest["files"]:
        assert hashlib.sha256(files[entry["path"]]).hexdigest() == entry["sha256"]
    readme = files["README.md"].decode().lower()
    for phrase in ("monitoring evidence only", "uncalibrated", "carbon not estimated"):
        assert phrase in readme
    assert "attribution" in readme
    assert "simulated data" not in readme  # Kariba is an observed project


def test_dossier_requires_audit_level(tenant_world: World) -> None:
    url = f"/projects/{KARIBA}/export/dossier"
    assert tenant_world.client("funder").get(url).status_code == 403  # view
    assert tenant_world.client("ngo").get(url).status_code == 403  # contribute
    assert tenant_world.client("outsider").get(url).status_code == 404
    assert tenant_world.client("ref").get(url).status_code == 200  # owner
    assert tenant_world.client("auditor").get(url).status_code == 200  # audit


def test_dossier_is_audited_and_deterministic(tenant_world: World) -> None:
    url = f"/projects/{KARIBA}/export/dossier"
    a = tenant_world.client("ref").get(url).content
    b = tenant_world.client("ref").get(url).content
    assert a == b
    with tenant_world.sessions() as db:
        rows = list(
            db.execute(
                select(AuditEventRow).where(AuditEventRow.action == "export.download")
            ).scalars()
        )
    assert len(rows) == 2
    for row in rows:  # each download is audited and names the ledger record that sealed it
        assert row.details["format"] == "dossier"
        assert row.details["ledger_record_id"].startswith("AUDIT-")
    assert rows[0].details["ledger_record_id"] != rows[1].details["ledger_record_id"]


def _keys(node: Any) -> set[str]:
    if isinstance(node, dict):
        return set(node) | {k for v in node.values() for k in _keys(v)}
    if isinstance(node, list):
        return {k for v in node for k in _keys(v)}
    return set()


def test_simulated_dossier_carries_the_banner(tenant_world: World) -> None:
    r = tenant_world.client("ref").get(f"/projects/{MIKOKO}/export/dossier")
    assert r.status_code == 200
    files = _zip(r.content)
    assert "SIMULATED DATA" in files["README.md"].decode()
    assert json.loads(files["provenance.json"])["data_mode"] == "simulated"
    keys = _keys(json.loads(files["assessment.json"])) | _keys(json.loads(files["provenance.json"]))
    assert not [k for k in keys if "carbon" in k.lower() or "tco2" in k.lower()]


# --- fix round 1 -------------------------------------------------------------------------------


def test_portfolio_row_degrades_when_the_assessment_raises(tenant_world, monkeypatch) -> None:
    from groundtruth.platform.api import portfolio as mod

    real = mod.build_project_assessment

    def flaky(project, **kw):  # type: ignore[no-untyped-def]
        if project.slug == KARIBA:
            raise RuntimeError("boom")
        return real(project, **kw)

    monkeypatch.setattr(mod, "build_project_assessment", flaky)
    r = tenant_world.client("ref").get("/orgs/reference/portfolio")
    assert r.status_code == 200
    body = r.json()
    rows = _by_slug(body["projects"] + body["simulated"])
    bad = rows[KARIBA]
    assert bad["degraded"] is True and bad["degraded_reason"] == "assessment unavailable"
    assert (bad["assessment_level"], bad["level_name"]) == (0, "Not assessable")
    assert bad["top_recommendation"] is None and bad["attribution_verdict"] is None
    assert bad["evidence_confidence"] is None
    others = [v for k, v in rows.items() if k != KARIBA]
    assert others and all(not o["degraded"] for o in others)


def test_portfolio_survives_a_corrupt_cache(tenant_world, monkeypatch, tmp_path) -> None:
    from groundtruth.platform.config import get_settings

    cache = tmp_path / "processed" / "stac_cache"
    cache.mkdir(parents=True)
    for ind in ("ndvi", "evi", "ndmi", "nbr"):
        (cache / f"{KARIBA}_{ind}.json").write_text("{not json", encoding="utf-8")
        (cache / f"{KARIBA}-{ind}.json").write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(get_settings(), "data_dir", tmp_path)
    r = tenant_world.client("ref").get("/orgs/reference/portfolio")
    assert r.status_code == 200
    rows = _by_slug(r.json()["projects"] + r.json()["simulated"])
    assert KARIBA in rows and rows[KARIBA]["assessment_level"] == 0
    assert MIKOKO in rows and not rows[MIKOKO]["degraded"]


def test_regrant_at_same_level_is_a_noop_but_audited(tenant_world: World) -> None:
    _grant(tenant_world, MIKOKO, FUNDER, "view")
    with tenant_world.sessions() as db:
        before = db.execute(select(ProjectGrantRow)).scalars().all()
        snap = [(g.id, g.created_at, g.granted_by, g.level) for g in before]
    assert _grant(tenant_world, MIKOKO, FUNDER, "view").status_code == 201
    with tenant_world.sessions() as db:
        after = [
            (g.id, g.created_at, g.granted_by, g.level)
            for g in db.execute(select(ProjectGrantRow)).scalars()
        ]
        n = len(
            list(
                db.execute(
                    select(AuditEventRow).where(AuditEventRow.action == "project.grant")
                ).scalars()
            )
        )
    assert after == snap and n == 2


def test_forged_cursor_cannot_read_another_orgs_audit(tenant_world: World) -> None:
    _grant(tenant_world, MIKOKO, FUNDER)
    with tenant_world.sessions() as db:
        other = (
            db.execute(
                select(AuditEventRow)
                .where(AuditEventRow.organization_id == tenant_world.org_ids["outsider-ngo"])
                .order_by(AuditEventRow.occurred_at.desc())
            )
            .scalars()
            .first()
        )
        assert other is not None
        raw = f"{(other.occurred_at.replace(year=2100)).isoformat()}|{other.id}"
        # cursors are opaque base64url; forge one in that format (the old raw form is rejected)
        forged = base64.urlsafe_b64encode(raw.encode()).rstrip(b"=").decode()
        legacy_raw = raw
        foreign = {
            e.id
            for e in db.execute(
                select(AuditEventRow).where(
                    AuditEventRow.organization_id != tenant_world.org_ids["reference"]
                )
            ).scalars()
        }
    assert (
        tenant_world.client("ref")
        .get("/orgs/reference/audit", params={"cursor": legacy_raw})
        .status_code
        == 422
    )
    r = tenant_world.client("ref").get("/orgs/reference/audit", params={"cursor": forged})
    assert r.status_code == 200
    ids = {e["id"] for e in r.json()["events"]}
    assert ids and not ids & foreign


def test_grantee_admin_and_owner_viewer_cannot_manage_grants(tenant_world: World) -> None:
    admin = _add_member(tenant_world, "gadmin@example.org", "admin", "auditor", "demo-auditor")
    url = f"/projects/{KARIBA}/grants"
    assert admin.get(url).status_code == 403
    assert admin.post(url, json={"org_slug": FUNDER, "level": "view"}).status_code == 403
    assert admin.delete(f"{url}/{FUNDER}").status_code == 403
    viewer = _add_member(tenant_world, "oviewer@example.org", "viewer")
    assert viewer.post(url, json={"org_slug": FUNDER, "level": "view"}).status_code == 403
    assert viewer.delete(f"{url}/demo-funder").status_code == 403
