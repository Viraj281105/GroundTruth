"""Every route that takes a case, project, run or job id is project-scoped and authorized.

No access answers 404 (indistinguishable from "does not exist"); a visible project with too
low a level answers 403. The route list is read from the live ``app.routes`` so a new route
with one of these path parameters is covered the moment it is added.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parent))
from world import (
    GRANTED_CASE,
    PRIVATE_CASE,
    World,
    build_world,
    queue_run,
    store_completed_run,
)

from groundtruth.contracts.identifiers import new_run_id
from groundtruth.engine import run_analysis
from groundtruth.platform.api import tiles
from groundtruth.platform.api.app import app
from groundtruth.platform.cases.registry import get_case
from groundtruth.platform.config import get_settings
from groundtruth.platform.datasets.access import synthetic_access
from groundtruth.platform.store.models import (
    AnalysisRunRow,
    AuditEventRow,
    JobRow,
)

pytestmark = pytest.mark.usefixtures("_fast_scrypt")
REPO = Path(__file__).resolve().parents[2]
SCOPED_PARAMS = ("{case_id}", "{project_id}", "{run_id}", "{job_id}")


@pytest.fixture(scope="module")
def completed():
    """A real finished run on SIMULATED DATA for Kariba (kept small: one engine call)."""
    request = get_case(GRANTED_CASE).to_request(data_mode="simulated", seed=20260101)
    return run_analysis(request, synthetic_access(request, true_effect=0.06))


@pytest.fixture
def world(client, sessions) -> World:
    return build_world(client, sessions)


# --- route enumeration ------------------------------------------------------------------


def _walk(routes, prefix: str = ""):
    for route in routes:
        original = getattr(route, "original_router", None)
        if original is not None:  # an included router (FastAPI >= 0.13x keeps them nested)
            yield from _walk(original.routes, prefix + route.include_context.prefix)
        elif hasattr(route, "methods") and hasattr(route, "path"):
            yield route, prefix + route.path


def scoped_routes() -> list[tuple[str, str]]:
    found = {
        (method, path)
        for route, path in _walk(app.routes)
        for method in route.methods - {"HEAD", "OPTIONS"}
        if any(p in path for p in SCOPED_PARAMS)
    }
    return sorted(found)


def _fill(path: str, *, case_id: str, project_id: str, run_id: str) -> str:
    return (
        path.replace("{case_id}", case_id)
        .replace("{project_id}", project_id)
        .replace("{run_id}", run_id)
        .replace("{job_id}", run_id)
    )


def _call(client, method: str, path: str):
    body: dict[str, Any] | None = {"synthetic": True} if method == "POST" else None
    return client.request(method, path, json=body)


def test_enumeration_finds_the_known_scoped_routes() -> None:
    routes = set(scoped_routes())
    assert {
        ("GET", "/runs/{run_id}"),
        ("GET", "/jobs/{run_id}"),
        ("POST", "/jobs/{run_id}/cancel"),
        ("GET", "/jobs/{job_id}/events"),
        ("GET", "/cases/{case_id}"),
        ("POST", "/cases/{case_id}/verify"),
        ("GET", "/cases/{case_id}/boundary.geojson"),
        ("GET", "/cases/{case_id}/export/csv"),
        ("GET", "/cases/{case_id}/export/pdf"),
        ("GET", "/projects/{project_id}"),
    } <= routes
    assert len(routes) >= 10


def test_every_project_route_isolated(world: World) -> None:
    """An org-B user driving any scoped route against an org-A resource gets 404."""
    run_id = queue_run(world.sessions, PRIVATE_CASE, world.project_ids[PRIVATE_CASE])
    outsider = world.client("outsider")
    assert scoped_routes()
    for method, template in scoped_routes():
        path = _fill(
            template,
            case_id=PRIVATE_CASE,
            project_id=world.project_ids[PRIVATE_CASE],
            run_id=run_id,
        )
        response = _call(outsider, method, path)
        assert response.status_code == 404, (method, template, response.status_code, response.text)


def test_every_project_route_isolated_for_unknown_ids(world: World) -> None:
    """A made-up id is the same 404 as someone else's id."""
    outsider = world.client("outsider")
    for method, template in scoped_routes():
        path = _fill(
            template, case_id="no-such-case", project_id="no-such-project", run_id="run_nope"
        )
        assert _call(outsider, method, path).status_code == 404, (method, template)


def test_every_project_route_requires_a_session(world: World, client) -> None:
    from authhelpers import new_client

    anonymous = new_client(client)
    for method, template in scoped_routes():
        path = _fill(
            template,
            case_id=GRANTED_CASE,
            project_id=world.project_ids[GRANTED_CASE],
            run_id="run_x",
        )
        response = _call(anonymous, method, path)
        assert response.status_code == 401, (method, template, response.status_code)


def test_owner_reads_the_same_routes_it_denies_others(world: World, completed) -> None:
    """The substitution is right: the owning org gets through (guards against vacuous 404s)."""
    run_id = store_completed_run(world.sessions, completed, world.project_ids[GRANTED_CASE])
    ref = world.client("ref")
    for method, template in scoped_routes():
        if (
            method != "GET"
            or "/export/" in template
            or template.endswith("/events")
            or "{doc_id}" in template  # needs a real document; see test_project_documents.py
            or "{ingestion_id}"
            in template  # needs a real request; see test_observation_ingestion.py
        ):
            continue
        path = _fill(
            template,
            case_id=GRANTED_CASE,
            project_id=world.project_ids[GRANTED_CASE],
            run_id=run_id,
        )
        assert _call(ref, method, path).status_code == 200, (method, template)


# --- run lists ---------------------------------------------------------------------------


def test_runs_list_scoped_to_org(world: World, completed) -> None:
    kariba_run = store_completed_run(world.sessions, completed, world.project_ids[GRANTED_CASE])
    private_run = queue_run(world.sessions, PRIVATE_CASE, world.project_ids[PRIVATE_CASE])
    orphan = queue_run(world.sessions, "alto-mayo-redd", None)

    def ids(who: str) -> set[str]:
        r = world.client(who).get("/runs")
        assert r.status_code == 200, r.text
        return {item["run_id"] for item in r.json()["items"]}

    assert ids("ref") == {kariba_run, private_run}  # owner sees its own; NULL project: nobody
    assert ids("funder") == {kariba_run}  # granted Kariba only
    assert ids("auditor") == {kariba_run}
    assert ids("outsider") == set()
    assert orphan not in ids("ref")


def test_runs_list_filters_still_apply_inside_the_scope(world: World, completed) -> None:
    store_completed_run(world.sessions, completed, world.project_ids[GRANTED_CASE])
    queue_run(world.sessions, PRIVATE_CASE, world.project_ids[PRIVATE_CASE])
    only = world.client("ref").get("/runs", params={"case_id": GRANTED_CASE}).json()["items"]
    assert [i["case_id"] for i in only] == [GRANTED_CASE]


def test_runs_list_cursor_survives_a_grant_scope(world: World) -> None:
    for n in range(3):
        queue_run(world.sessions, GRANTED_CASE, world.project_ids[GRANTED_CASE], seed_value=100 + n)
    first = world.client("funder").get("/runs", params={"limit": 2}).json()
    assert len(first["items"]) == 2 and first["next_cursor"]
    second = (
        world.client("funder")
        .get("/runs", params={"limit": 2, "cursor": first["next_cursor"]})
        .json()
    )
    assert len(second["items"]) == 1


def test_a_run_without_a_project_is_invisible_to_everyone(world: World) -> None:
    orphan = queue_run(world.sessions, GRANTED_CASE, None, seed_value=7)
    for who in ("ref", "auditor", "outsider"):
        c = world.client(who)
        assert c.get(f"/runs/{orphan}").status_code == 404, who
        assert c.get(f"/jobs/{orphan}").status_code == 404, who
        assert c.post(f"/jobs/{orphan}/cancel").status_code == 404, who
        assert c.get(f"/jobs/{orphan}/events").status_code == 404, who


def test_run_detail_withholds_the_bundle_below_diagnostics(world: World, completed) -> None:
    run_id = store_completed_run(world.sessions, completed, world.project_ids[GRANTED_CASE])
    seen: dict[str, Any] = {}
    for who in ("ref", "auditor", "ngo", "funder"):
        r = world.client(who).get(f"/runs/{run_id}", params={"include_report": "true"})
        assert r.status_code == 200, (who, r.text)
        seen[who] = r.json()
    for who in ("ref", "auditor"):
        assert seen[who]["bundle"] is not None and seen[who]["report_markdown"]
    for who in ("ngo", "funder"):  # redaction removes fields; metadata is the same values
        assert seen[who]["bundle"] is None and seen[who]["report_markdown"] is None
        assert seen[who]["has_bundle"] is True
        assert seen[who]["verdict_label"] == seen["auditor"]["verdict_label"]


def test_compare_needs_both_runs_and_diagnostics(world: World, completed) -> None:
    a = store_completed_run(world.sessions, completed, world.project_ids[GRANTED_CASE])
    b = store_completed_run(
        world.sessions,
        completed.model_copy(update={"run_id": new_run_id()}),
        world.project_ids[GRANTED_CASE],
    )
    hidden = queue_run(world.sessions, PRIVATE_CASE, world.project_ids[PRIVATE_CASE])
    auditor = world.client("auditor")
    assert auditor.get("/runs/compare", params={"baseline": a, "candidate": b}).status_code == 200
    assert (
        auditor.get("/runs/compare", params={"baseline": a, "candidate": hidden}).status_code == 404
    )
    assert (
        auditor.get("/runs/compare", params={"baseline": hidden, "candidate": a}).status_code == 404
    )
    assert (
        world.client("funder")
        .get("/runs/compare", params={"baseline": a, "candidate": b})
        .status_code
        == 403
    )


# --- jobs --------------------------------------------------------------------------------


def test_job_requested_by_filled(world: World) -> None:
    ref = world.client("ref")
    r = ref.post("/jobs", json={"case_id": GRANTED_CASE})
    assert r.status_code == 202, r.text
    run_id = r.json()["run_id"]
    with world.sessions() as db:
        run = db.get(AnalysisRunRow, run_id)
        job = db.get(JobRow, run_id)
        assert run is not None and job is not None
        assert run.requested_by == world.user_ids["ref"]
        assert run.project_id == job.project_id == world.project_ids[GRANTED_CASE]
        audit = db.execute(
            select(AuditEventRow).where(AuditEventRow.action == "run.start")
        ).scalar_one()
        assert audit.actor_user_id == world.user_ids["ref"]
        assert audit.resource_id == run_id and audit.outcome == "success"
        assert audit.details["project_id"] == world.project_ids[GRANTED_CASE]
    # and the caller can read it back; a grantee can too
    assert ref.get(f"/jobs/{run_id}").status_code == 200
    assert world.client("funder").get(f"/jobs/{run_id}").status_code == 200


def test_cache_hit_on_an_unfiled_run_adopts_the_project(world: World) -> None:
    orphan = queue_run(world.sessions, GRANTED_CASE, None, seed_value=20260101)
    r = world.client("ref").post("/jobs", json={"case_id": GRANTED_CASE})
    assert r.status_code == 200 and r.json()["run_id"] == orphan, r.text
    with world.sessions() as db:
        assert db.get(AnalysisRunRow, orphan).project_id == world.project_ids[GRANTED_CASE]
    assert world.client("ref").get(f"/jobs/{orphan}").status_code == 200


@pytest.mark.parametrize("who", ["ngo", "funder", "auditor", "government"])
def test_a_grant_never_lets_a_tenant_start_or_cancel_a_run(world: World, who: str) -> None:
    run_id = queue_run(world.sessions, GRANTED_CASE, world.project_ids[GRANTED_CASE])
    c = world.client(who)
    assert c.post("/jobs", json={"case_id": GRANTED_CASE}).status_code == 403
    assert c.post(f"/jobs/{run_id}/cancel").status_code == 403
    assert c.post(f"/cases/{GRANTED_CASE}/verify", json={"synthetic": True}).status_code == 403
    with world.sessions() as db:
        assert db.get(AnalysisRunRow, run_id).status == "queued"
        assert (
            db.execute(
                select(AuditEventRow).where(AuditEventRow.action.in_(["run.start", "run.cancel"]))
            ).first()
            is None
        )


def test_cancel_is_audited(world: World) -> None:
    run_id = queue_run(world.sessions, GRANTED_CASE, world.project_ids[GRANTED_CASE])
    r = world.client("ref").post(f"/jobs/{run_id}/cancel")
    assert r.status_code == 200, r.text
    with world.sessions() as db:
        event = db.execute(
            select(AuditEventRow).where(AuditEventRow.action == "run.cancel")
        ).scalar_one()
        assert event.resource_id == run_id and event.actor_user_id == world.user_ids["ref"]


def test_a_viewer_role_in_the_owning_org_cannot_start_runs(world: World) -> None:
    from groundtruth.platform.store.models import MembershipRow

    with world.sessions() as db:
        db.execute(
            MembershipRow.__table__.update()
            .where(MembershipRow.user_id == world.user_ids["ref"])
            .values(role="viewer")
        )
        db.commit()
    ref = world.client("ref")
    assert ref.post("/jobs", json={"case_id": GRANTED_CASE}).status_code == 403
    assert ref.get(f"/cases/{GRANTED_CASE}").status_code == 200  # reads stay open


def test_sse_is_authorized_before_the_stream_opens(world: World) -> None:
    """A queued job would hold a stream open for minutes; a denial must return at once."""
    run_id = queue_run(world.sessions, PRIVATE_CASE, world.project_ids[PRIVATE_CASE])
    response = world.client("outsider").get(f"/jobs/{run_id}/events")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")


# --- /cases ------------------------------------------------------------------------------


def test_case_list_and_detail_are_scoped(world: World) -> None:
    assert world.client("outsider").get("/cases").json() == []
    funder = {c["case_id"] for c in world.client("funder").get("/cases").json()}
    assert funder == {GRANTED_CASE}
    ref = {c["case_id"] for c in world.client("ref").get("/cases").json()}
    assert {GRANTED_CASE, PRIVATE_CASE} <= ref
    assert world.client("funder").get(f"/cases/{GRANTED_CASE}").status_code == 200
    assert world.client("funder").get(f"/cases/{PRIVATE_CASE}").status_code == 404


def test_hardcoded_endpoints_removed(world: World) -> None:
    for who in ("ref", "funder", "outsider"):
        for suffix in ("causal-readiness", "real-observations"):
            r = world.client(who).get(f"/cases/{GRANTED_CASE}/{suffix}")
            assert r.status_code == 404, (who, suffix)
    paths = {path for _, path in _walk(app.routes)}
    assert not any("causal-readiness" in p or "real-observations" in p for p in paths)


# --- exports, boundary, tiles ------------------------------------------------------------


@pytest.mark.parametrize("who", ["ngo", "funder", "auditor", "ref"])
def test_every_grant_level_may_export_and_it_is_audited(world: World, who: str) -> None:
    r = world.client(who).get(f"/cases/{GRANTED_CASE}/export/csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    with world.sessions() as db:
        event = db.execute(
            select(AuditEventRow).where(AuditEventRow.action == "export.download")
        ).scalar_one()
        assert event.actor_user_id == world.user_ids[who] and event.outcome == "success"
        assert event.resource_id == world.project_ids[GRANTED_CASE]
        assert event.details["format"] == "csv"


def test_pdf_export_is_audited_too(world: World) -> None:
    r = world.client("funder").get(f"/cases/{GRANTED_CASE}/export/pdf")
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    with world.sessions() as db:
        event = db.execute(
            select(AuditEventRow).where(AuditEventRow.action == "export.download")
        ).scalar_one()
        assert event.details["format"] == "pdf"


def test_denied_export_is_not_logged_as_a_download(world: World) -> None:
    assert world.client("outsider").get(f"/cases/{GRANTED_CASE}/export/csv").status_code == 404
    with world.sessions() as db:
        assert (
            db.execute(
                select(AuditEventRow).where(AuditEventRow.action == "export.download")
            ).first()
            is None
        )


def test_boundary_needs_a_grant(world: World) -> None:
    assert world.client("funder").get(f"/cases/{GRANTED_CASE}/boundary.geojson").status_code == 200
    assert (
        world.client("outsider").get(f"/cases/{GRANTED_CASE}/boundary.geojson").status_code == 404
    )


def test_tiles_need_a_session(world: World, client) -> None:
    from authhelpers import new_client

    assert new_client(client).get("/tiles/3/4/4.mvt").status_code == 401


def test_tiles_without_postgis_are_503_for_a_signed_in_user(world: World, monkeypatch) -> None:
    monkeypatch.setattr(
        tiles,
        "get_settings",
        lambda: get_settings().model_copy(update={"database_url": "sqlite:///x.db"}),
    )
    r = world.client("funder").get("/tiles/3/4/4.mvt")
    assert r.status_code == 503 and r.json()["detail"]["code"] == "postgis_not_configured"


def test_tiles_are_limited_to_the_callers_projects(world: World, monkeypatch) -> None:
    captured: list[dict[str, Any]] = []

    class _Result:
        def scalar_one(self) -> bytes:
            return b""

    class _Conn:
        def __enter__(self) -> _Conn:
            return self

        def __exit__(self, *exc: object) -> None:
            return None

        def execute(self, statement: Any, params: dict[str, Any]) -> _Result:
            captured.append(params)
            return _Result()

    class _Engine:
        def connect(self) -> _Conn:
            return _Conn()

    monkeypatch.setattr(
        tiles,
        "get_settings",
        lambda: get_settings().model_copy(update={"database_url": "postgresql://x/y"}),
    )
    monkeypatch.setattr(tiles, "_engine", lambda url: _Engine())
    for who, expected in (("funder", [GRANTED_CASE]), ("outsider", [])):
        assert world.client(who).get("/tiles/3/4/4.mvt").status_code == 200
        assert captured[-1]["case_ids"] == expected, who
    world.client("ref").get("/tiles/3/4/4.mvt")
    assert {GRANTED_CASE, PRIVATE_CASE} <= set(captured[-1]["case_ids"])


# --- deployment profile ------------------------------------------------------------------


def test_compose_and_helm_force_auth() -> None:
    compose = yaml.safe_load((REPO / "docker-compose.yml").read_text(encoding="utf-8"))
    assert str(compose["services"]["api"]["environment"]["AUTH_REQUIRED"]).lower() == "true"
    values = yaml.safe_load(
        (REPO / "infrastructure/helm/groundtruth/values.yaml").read_text(encoding="utf-8")
    )
    assert str(values["config"]["AUTH_REQUIRED"]).lower() == "true"
    configmap = (REPO / "infrastructure/helm/groundtruth/templates/configmap.yaml").read_text(
        encoding="utf-8"
    )
    assert re.search(r"range \$k, \$v := \.Values\.config", configmap)  # values reach the pods


def test_startup_warns_when_auth_is_off(monkeypatch, caplog) -> None:
    from fastapi.testclient import TestClient

    monkeypatch.setattr(get_settings(), "auth_required", False)
    with caplog.at_level("WARNING", logger="groundtruth.auth"), TestClient(app):
        pass
    assert any("AUTH_REQUIRED is false" in m for m in caplog.messages)


def test_startup_is_quiet_when_auth_is_on(monkeypatch, caplog) -> None:
    from fastapi.testclient import TestClient

    monkeypatch.setattr(get_settings(), "auth_required", True)
    with caplog.at_level("WARNING", logger="groundtruth.auth"), TestClient(app):
        pass
    assert not any("AUTH_REQUIRED is false" in m for m in caplog.messages)


@pytest.mark.requires_local_data("data/processed/climate_cache/kariba_chirps_climate.json")
def test_the_quarantined_landsat_cache_is_never_searched(tmp_path, monkeypatch) -> None:
    from groundtruth.contracts.errors import DataUnavailableError
    from groundtruth.platform.datasets import access

    data_dir = tmp_path / "data"
    (data_dir / "processed" / "landsat_cache").mkdir(parents=True)
    settings = get_settings()
    monkeypatch.setattr(settings, "data_dir", data_dir)
    import groundtruth.platform.config as config

    monkeypatch.setattr(config, "REPO_ROOT", tmp_path / "no-repo")
    request = get_case(GRANTED_CASE).to_request(data_mode="observed", seed=1)
    with pytest.raises(DataUnavailableError):
        access.real_stac_access(request)
    (data_dir / "processed" / "stac_cache").mkdir()
    assert access.real_stac_access(request) is not None
