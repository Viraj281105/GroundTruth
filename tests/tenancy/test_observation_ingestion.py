"""Satellite observation ingestion for user-created project boundaries.

The satellite provider is replaced by a fake that builds scene chips and feeds them through the
*real* ``reduce_aoi_scenes_to_series`` and ``AOIObservationCache``, so every bundle carries genuine
pipeline provenance. Everything else (validation, queue, claiming, status, coverage summary, ledger,
loader, readiness, tenant isolation) is the production code.
"""

from __future__ import annotations

import concurrent.futures
import dataclasses
import hashlib
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parent))
from world import GRANTED_CASE, World

from groundtruth.contracts.errors import DataUnavailableError
from groundtruth.data_access.aoi_pipeline import (
    AOIObservationBundle,
    SceneRasterChip,
    reduce_aoi_scenes_to_series,
)
from groundtruth.data_access.stac import SceneDescriptor
from groundtruth.platform.audit.ledger import AuditLedger
from groundtruth.platform.config import get_settings
from groundtruth.platform.projects import ingestion
from groundtruth.platform.projects.data import load_observations
from groundtruth.platform.store.models import (
    AuditEventRow,
    ObservationIngestionRow,
    ProjectRow,
)

pytestmark = pytest.mark.usefixtures("_fast_scrypt")

SQUARE = {
    "type": "Polygon",
    "coordinates": [[[30.0, -1.0], [30.1, -1.0], [30.1, -0.9], [30.0, -0.9], [30.0, -1.0]]],
}
BASE = {"start_year": 2021, "end_year": 2023, "window_start": "06-01", "window_end": "06-30"}


@pytest.fixture(autouse=True)
def _isolated_dirs(tmp_path, monkeypatch):
    """Boundaries, documents and the observation cache all go to a temp dir, never the repo."""
    s = get_settings()
    monkeypatch.setattr(s, "cases_dir", tmp_path / "cases")
    monkeypatch.setattr(s, "data_dir", tmp_path / "data")
    monkeypatch.setattr(s, "project_documents_dir", tmp_path / "docs")
    monkeypatch.setattr(s, "observation_ingestion_enabled", True)


def _create_project(
    world: World, who: str = "outsider", slug: str = "outsider-ngo"
) -> dict[str, Any]:
    r = world.client(who).post(
        f"/orgs/{slug}/projects",
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
    return r.json()


def _chip(scene: str, when: str, *, nir: float, red: float) -> SceneRasterChip:
    desc = SceneDescriptor(
        id=scene,
        collection="sentinel-2-l2a",
        datetime=when,
        bbox=(30.0, -1.0, 30.1, -0.9),
        cloud_cover=5.0,
        assets=("B02", "B04", "B08", "B11", "B12", "SCL"),
        href=f"https://planetarycomputer.microsoft.com/api/stac/v1/items/{scene}",
        sensor="sentinel-2b",
        tile_id="35MQV",
    )
    full = lambda v: np.full((2, 2), float(v))  # noqa: E731
    return SceneRasterChip(
        descriptor=desc,
        bands_dn={
            "B02": full(1000),
            "B04": full(red),
            "B08": full(nir),
            "B11": full(3000),
            "B12": full(2000),
        },
        quality=np.full((2, 2), 4, dtype=int),  # SCL 4 = vegetation: clear
    )


def fake_provider(available: dict[int, float], calls: list[dict[str, Any]] | None = None):
    """A satellite-provider stand-in. ``available`` maps year -> NIR DN; other years have no scenes."""

    def fn(*, unit_id, aoi_geojson, years, indicators, cache, **kwargs):
        if calls is not None:
            calls.append({"unit_id": unit_id, "years": list(years), "kwargs": kwargs})
        chips: dict[int, list[SceneRasterChip]] = {}
        for y in years:
            nir = available.get(y)
            chips[y] = (
                [
                    _chip(f"S2_{y}_{i}", f"{y}-06-1{i}T08:00:00Z", nir=nir, red=2000)
                    for i in range(2)
                ]
                if nir is not None
                else []
            )
        out: dict[str, AOIObservationBundle] = {}
        for ind in indicators:
            b = reduce_aoi_scenes_to_series(
                unit_id=unit_id,
                aoi_geojson=aoi_geojson,
                chips_by_year=chips,
                indicator=ind,
                sensor="sentinel-2",
            )
            params = dict(b.provenance.parameters)
            params["raster_grid"] = {
                "crs": "EPSG:32735",
                "resolution_m": 100.0,
                "height": 2,
                "width": 2,
            }
            b = AOIObservationBundle(
                unit_id=b.unit_id,
                indicator=b.indicator,
                bbox=b.bbox,
                records=b.records,
                data_origin=b.data_origin,
                catalog_url=b.catalog_url,
                provenance=b.provenance.model_copy(update={"parameters": params}),
            )
            cache.put(b)
            out[ind] = b
        return out

    return fn


def _run(world: World, project_id: str, provider) -> str:
    """Request through the API, then let the worker code run it."""
    ran = ingestion.process_pending(world.sessions, "test-worker", limit=1, ingest_fn=provider)
    assert ran == 1
    return project_id


def _rows(world: World, project_id: str) -> list[ObservationIngestionRow]:
    with world.sessions() as db:
        return list(
            db.execute(
                select(ObservationIngestionRow)
                .where(ObservationIngestionRow.project_id == project_id)
                .order_by(ObservationIngestionRow.created_at)
            ).scalars()
        )


def _post(world: World, project_id: str, body: dict[str, Any] | None = None, who: str = "outsider"):
    return world.client(who).post(
        f"/projects/{project_id}/observations/ingestions", json=body or BASE
    )


# --- validation -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("override", "fragment"),
    [
        ({"start_year": 2010}, "between 2017"),
        ({"start_year": 2024, "end_year": 2022}, "before the start"),
        ({"start_year": 2017, "end_year": 2030}, "between 2017"),
        ({"start_year": 2017, "end_year": 2023, "max_scenes_per_year": 9}, "scenes one request"),
        ({"window_start": "13-01"}, "month and day"),
        ({"window_start": "09-01", "window_end": "03-01"}, "start before it ends"),
        ({"max_cloud_cover": 95}, "between 0 and 80"),
        ({"indicators": ["ndvi", "banana"]}, "Unsupported indicator"),
        ({"resolution_m": 5}, "Resolution must be"),
        ({"resolution_m": 900}, "Resolution must be"),
    ],
)
def test_invalid_requests_are_rejected_with_a_reason(
    tenant_world: World, override, fragment
) -> None:
    pid = _create_project(tenant_world)["id"]
    r = _post(tenant_world, pid, {**BASE, **override})
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert fragment in detail["message"]
    assert detail["code"] == "invalid_request"
    assert _rows(tenant_world, pid) == []  # nothing queued


def test_an_area_too_large_for_the_grid_limit_is_refused(tenant_world: World) -> None:
    big = {"type": "Polygon", "coordinates": [[[20, -10], [30, -10], [30, 0], [20, 0], [20, -10]]]}
    r = tenant_world.client("outsider").post(
        "/orgs/outsider-ngo/projects",
        data={
            "name": "Huge",
            "country": "Zambia",
            "ecosystem": "miombo",
            "intervention": "reforestation",
            "treatment_start_year": "2019",
        },
        files={"boundary": ("b.geojson", json.dumps(big).encode())},
    )
    pid = r.json()["id"]
    res = _post(tenant_world, pid, {**BASE, "resolution_m": 20})
    assert res.status_code == 422
    assert "too large" in res.json()["detail"]["message"]


def test_validate_request_defaults_and_ndvi_is_always_stored() -> None:
    p = ingestion.validate_request({"start_year": 2022}, (30.0, -1.0, 30.1, -0.9))
    assert (p.start_year, p.end_year, p.window_start, p.window_end) == (
        2022,
        2022,
        "06-01",
        "06-30",
    )
    assert p.indicators == ("ndvi", "evi")
    p2 = ingestion.validate_request(
        {"start_year": 2022, "indicators": ["evi", "nbr"]}, (30.0, -1.0, 30.1, -0.9)
    )
    assert p2.indicators[0] == "ndvi" and set(p2.indicators) == {"ndvi", "evi", "nbr"}


# --- queue and permissions ---------------------------------------------------------------------------


def test_request_is_queued_visible_and_single_flight(tenant_world: World) -> None:
    pid = _create_project(tenant_world)["id"]
    r = _post(tenant_world, pid)
    assert r.status_code == 202, r.text
    view = r.json()
    assert view["status"] == "queued" and view["result"] is None
    assert view["params"]["indicators"] == ["ndvi", "evi"]

    lst = tenant_world.client("outsider").get(f"/projects/{pid}/observations/ingestions").json()
    assert lst["enabled"] is True and lst["active"] is True
    assert lst["limits"]["first_year"] == 2017
    assert [i["id"] for i in lst["ingestions"]] == [view["id"]]

    again = _post(tenant_world, pid)
    assert again.status_code == 409 and again.json()["detail"]["code"] == "ingestion_in_progress"


def test_a_queued_request_can_be_cancelled_and_then_replaced(tenant_world: World) -> None:
    pid = _create_project(tenant_world)["id"]
    rid = _post(tenant_world, pid).json()["id"]
    c = tenant_world.client("outsider").post(
        f"/projects/{pid}/observations/ingestions/{rid}/cancel"
    )
    assert c.status_code == 200 and c.json()["status"] == "cancelled"
    assert _post(tenant_world, pid).status_code == 202

    # a running (claimed) request cannot be cancelled
    claimed = ingestion.claim_next(tenant_world.sessions, "w1")
    r2 = tenant_world.client("outsider").post(
        f"/projects/{pid}/observations/ingestions/{claimed}/cancel"
    )
    assert r2.status_code == 409 and r2.json()["detail"]["code"] == "cannot_cancel"


def test_permissions_and_tenant_isolation(tenant_world: World) -> None:
    pid = _create_project(tenant_world)["id"]
    base = f"/projects/{pid}/observations/ingestions"
    anon = tenant_world.client("outsider").__class__(
        tenant_world.client("outsider").app, base_url=str(tenant_world.client("outsider").base_url)
    )
    assert anon.get(base).status_code == 401
    assert anon.post(base, json=BASE).status_code == 401
    # another organization cannot see or request anything for this project
    assert tenant_world.client("ngo").get(base).status_code == 404
    assert _post(tenant_world, pid, who="ngo").status_code == 404

    # a view-level grantee of a project may read statuses but not request ingestion
    k = f"/projects/{GRANTED_CASE}/observations/ingestions"
    assert tenant_world.client("funder").get(k).status_code == 200
    assert tenant_world.client("funder").post(k, json=BASE).status_code == 403


def test_an_ingestion_of_another_project_is_invisible(tenant_world: World) -> None:
    a = _create_project(tenant_world)["id"]
    rid = _post(tenant_world, a).json()["id"]
    other = tenant_world.client("ref").get(f"/projects/{GRANTED_CASE}").json()["id"]
    r = tenant_world.client("ref").get(f"/projects/{other}/observations/ingestions/{rid}")
    assert r.status_code == 404


def test_disabled_ingestion_is_refused_clearly(tenant_world: World, monkeypatch) -> None:
    pid = _create_project(tenant_world)["id"]
    monkeypatch.setattr(get_settings(), "observation_ingestion_enabled", False)
    r = _post(tenant_world, pid)
    assert r.status_code == 503 and r.json()["detail"]["code"] == "ingestion_disabled"
    inv = tenant_world.client("outsider").get(f"/projects/{pid}/evidence-inventory").json()
    assert inv["observation_ingestion"]["available"] is False


# --- running: success, partial, failure -------------------------------------------------------------


def test_a_complete_run_stores_observations_that_the_platform_then_uses(
    tenant_world: World,
) -> None:
    pid = _create_project(tenant_world)["id"]
    _post(tenant_world, pid, {**BASE, "start_year": 2017, "end_year": 2023})
    calls: list[dict[str, Any]] = []
    provider = fake_provider({y: 6000 + 100 * (y - 2017) for y in range(2017, 2024)}, calls)
    _run(tenant_world, pid, provider)

    (row,) = _rows(tenant_world, pid)
    assert row.status == "succeeded", row.status_detail
    assert row.error_code is None and row.worker_id == "test-worker"
    assert calls[0]["unit_id"] == pid  # the project's own id, never a case id
    assert calls[0]["kwargs"]["multi_tile"] is True
    assert calls[0]["kwargs"]["date_window"] == ("06-01", "06-30")
    res = row.result
    assert res["coverage"]["complete_years"] == list(range(2017, 2024))
    assert res["coverage"]["years_without_data"] == [] and res["coverage"]["partial_years"] == []
    assert all(y["state"] == "observed" and y["n_scenes"] == 2 for y in res["years"])
    assert res["limitations"] and "not tree survival" in res["limitations"][0]

    # the stored bundle is the one the platform reads, keyed by the project id
    stored = Path(get_settings().data_dir) / "processed" / "stac_cache" / f"{pid}__ndvi.json"
    assert stored.is_file()
    assert (
        res["stored_bundles"]["ndvi"]["sha256"] == hashlib.sha256(stored.read_bytes()).hexdigest()
    )

    with tenant_world.sessions() as db:
        project = db.get(ProjectRow, pid)
        obs = load_observations(project, "ndvi")
    assert obs.status == "available" and obs.bundle is not None
    assert [r.year for r in obs.bundle.records] == list(range(2017, 2024))

    # ...and so do the existing observation, readiness and assessment endpoints
    c = tenant_world.client("outsider")
    series = c.get(f"/projects/{pid}/observations").json()
    assert series["status"] == "available"
    ready = {x["id"]: x for x in c.get(f"/projects/{pid}/readiness").json()["criteria"]}
    assert ready["observation_years"]["status"] != "unavailable"
    assessment = c.get(f"/projects/{pid}/assessment").json()
    assert assessment["level"] >= 1  # observed trajectory is now describable
    assert assessment["attribution"]["verdict"] == "Inconclusive"  # still no counterfactual
    assert "carbon" not in json.dumps(assessment).lower()


def test_the_series_names_the_collection_the_data_really_came_from(tenant_world: World) -> None:
    """The stored provenance text names an Earth Engine collection; the API must not repeat that."""
    pid = _create_project(tenant_world)["id"]
    _post(tenant_world, pid)
    _run(tenant_world, pid, fake_provider({2021: 6000, 2022: 6100, 2023: 6200}))
    series = tenant_world.client("outsider").get(f"/projects/{pid}/observations").json()
    assert "sentinel-2-l2a" in series["source"]
    assert "planetarycomputer.microsoft.com" in series["source"]
    assert "COPERNICUS/S2_SR_HARMONIZED" not in series["source"]


def test_each_ingestion_is_recorded_in_the_ledger_with_the_stored_hashes(
    tenant_world: World,
) -> None:
    pid = _create_project(tenant_world)["id"]
    _post(tenant_world, pid)
    _run(tenant_world, pid, fake_provider({2021: 6000, 2022: 6200, 2023: 6400}))
    (row,) = _rows(tenant_world, pid)
    assert row.ledger_record_id and row.ledger_record_id.startswith("AUDIT-")
    ledger = AuditLedger(tenant_world.sessions)
    rec = ledger.get_record_by_id(row.ledger_record_id)
    assert rec is not None and rec.record_kind == "observation.ingested"
    assert (
        rec.input_files_hashes["ndvi"] == f"sha256:{row.result['stored_bundles']['ndvi']['sha256']}"
    )
    assert rec.analytical_parameters["window_start"] == "06-01"
    assert ledger.verify_project(pid).status == "verified"


def test_missing_years_stay_empty_and_the_run_is_partial_never_complete(
    tenant_world: World,
) -> None:
    pid = _create_project(tenant_world)["id"]
    _post(tenant_world, pid)
    _run(tenant_world, pid, fake_provider({2021: 6000, 2023: 6400}))  # 2022 has no usable scene
    (row,) = _rows(tenant_world, pid)
    assert row.status == "partial"
    cov = row.result["coverage"]
    assert cov["complete_years"] == [2021, 2023] and cov["years_without_data"] == [2022]
    by_year = {y["year"]: y for y in row.result["years"]}
    assert by_year[2022]["state"] == "no_usable_data" and by_year[2022]["values"]["ndvi"] is None
    assert "2022" in row.status_detail and "not estimated" in row.status_detail
    assert any("2022" in lim and "not estimated" in lim for lim in row.result["limitations"])
    with tenant_world.sessions() as db:
        bundle = load_observations(db.get(ProjectRow, pid), "ndvi").bundle
    assert bundle is not None
    year_2022 = next(r for r in bundle.records if r.year == 2022)
    assert year_2022.evidence_state == "UNAVAILABLE"  # empty, not interpolated


def test_low_area_coverage_is_reported_as_partial_coverage() -> None:
    chips = {2022: [_chip("S2_2022_0", "2022-06-10T08:00:00Z", nir=6000, red=2000)]}
    b = reduce_aoi_scenes_to_series(
        unit_id="p", aoi_geojson=SQUARE, chips_by_year=chips, indicator="ndvi", sensor="sentinel-2"
    )
    low = dataclasses.replace(b.records[0], aoi_coverage_pct=41.0, is_spatially_complete=False)
    bundle = AOIObservationBundle(
        unit_id=b.unit_id,
        indicator=b.indicator,
        bbox=b.bbox,
        records=(low,),
        data_origin=b.data_origin,
        catalog_url=b.catalog_url,
        provenance=b.provenance,
    )
    params = ingestion.validate_request({"start_year": 2022}, (30.0, -1.0, 30.1, -0.9))
    out = ingestion.summarise({"ndvi": bundle}, params)
    assert out["coverage"]["partial_years"] == [2022] and out["coverage"]["complete_years"] == []
    assert out["years"][0]["state"] == "partial_coverage"
    assert out["years"][0]["aoi_coverage_pct"] == 41.0
    assert any("below 95%" in lim for lim in out["limitations"])


def test_no_usable_data_fails_and_stores_nothing_claimed_as_data(tenant_world: World) -> None:
    pid = _create_project(tenant_world)["id"]
    _post(tenant_world, pid)
    _run(tenant_world, pid, fake_provider({}))
    (row,) = _rows(tenant_world, pid)
    assert row.status == "failed" and row.error_code == "no_usable_observations"
    assert "wider season window" in row.status_detail
    assert row.ledger_record_id is None  # nothing was observed, so nothing is sealed as data


def test_provider_outage_is_recorded_plainly_without_a_stack_trace(tenant_world: World) -> None:
    pid = _create_project(tenant_world)["id"]
    _post(tenant_world, pid)

    def down(**_: Any):
        raise ConnectionError("HTTPSConnectionPool(host='secret-internal', port=443): timed out")

    _run(tenant_world, pid, down)
    (row,) = _rows(tenant_world, pid)
    assert row.status == "failed" and row.error_code == "provider_unreachable"
    assert "could not be reached" in row.status_detail
    assert "secret-internal" not in row.status_detail and "Traceback" not in row.status_detail
    assert ingestion.claim_next(tenant_world.sessions, "w") is None
    assert _post(tenant_world, pid).status_code == 202  # a failure does not block a retry


def test_no_scenes_found_gets_its_own_code(tenant_world: World) -> None:
    pid = _create_project(tenant_world)["id"]
    _post(tenant_world, pid)

    def none_found(**_: Any):
        raise DataUnavailableError("no Sentinel-2 scenes matched")

    _run(tenant_world, pid, none_found)
    (row,) = _rows(tenant_world, pid)
    assert row.error_code == "no_scenes_found" and "cloud limit" in row.status_detail


def test_unexpected_errors_are_contained(tenant_world: World) -> None:
    pid = _create_project(tenant_world)["id"]
    _post(tenant_world, pid)

    def boom(**_: Any):
        raise RuntimeError("kaboom with /home/secret/path")

    _run(tenant_world, pid, boom)
    (row,) = _rows(tenant_world, pid)
    assert row.status == "failed" and row.error_code == "processing_error"
    assert "secret/path" not in row.status_detail


def test_ingestions_never_cross_projects(tenant_world: World) -> None:
    a = _create_project(tenant_world)["id"]
    b = _create_project(tenant_world)["id"]
    _post(tenant_world, a)
    _run(tenant_world, a, fake_provider({2021: 6000, 2022: 6100, 2023: 6200}))
    with tenant_world.sessions() as db:
        assert load_observations(db.get(ProjectRow, a), "ndvi").status == "available"
        other = load_observations(db.get(ProjectRow, b), "ndvi")
    assert other.status == "unavailable" and "No ndvi observations" in (other.reason or "")


# --- robustness ---------------------------------------------------------------------------------------


def test_only_one_worker_can_claim_a_request(tenant_world: World) -> None:
    pid = _create_project(tenant_world)["id"]
    _post(tenant_world, pid)
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        got = list(
            pool.map(lambda i: ingestion.claim_next(tenant_world.sessions, f"w{i}"), range(6))
        )
    assert sum(1 for g in got if g) == 1


def test_a_dead_workers_request_is_failed_not_left_running(tenant_world: World) -> None:
    pid = _create_project(tenant_world)["id"]
    _post(tenant_world, pid)
    ingestion.claim_next(tenant_world.sessions, "dead-worker")
    long_ago = datetime.now(UTC) - timedelta(hours=3)
    with tenant_world.sessions() as db:
        r = db.execute(select(ObservationIngestionRow)).scalars().first()
        r.heartbeat_at = long_ago
        db.commit()
    assert ingestion.sweep_stale(tenant_world.sessions) == 1
    (row,) = _rows(tenant_world, pid)
    assert row.status == "failed" and row.error_code == "interrupted"
    assert "Nothing was stored" in row.status_detail


def test_requests_and_outcomes_are_audited(tenant_world: World) -> None:
    pid = _create_project(tenant_world)["id"]
    _post(tenant_world, pid)
    _run(tenant_world, pid, fake_provider({2021: 6000, 2022: 6100, 2023: 6200}))
    with tenant_world.sessions() as db:
        actions = {e.action for e in db.execute(select(AuditEventRow)).scalars()}
    assert {"observations.ingest_requested", "observations.ingest"} <= actions


def test_the_dossier_for_an_ingested_project_contains_the_observations(tenant_world: World) -> None:
    import io
    import zipfile

    pid = _create_project(tenant_world)["id"]
    _post(tenant_world, pid)
    _run(tenant_world, pid, fake_provider({2021: 6000, 2022: 6100, 2023: 6200}))
    r = tenant_world.client("outsider").get(f"/projects/{pid}/export/dossier")
    assert r.status_code == 200
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        obs = z.read("observations.csv").decode()
    assert "2021" in obs and "2023" in obs and len(obs.splitlines()) > 3
