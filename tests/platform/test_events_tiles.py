"""SSE job events and the boundary / tile endpoints."""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from groundtruth.platform.api import events, tiles
from groundtruth.platform.api.app import app
from groundtruth.platform.api.dependencies import get_jobs
from groundtruth.platform.config import get_settings


class _View:
    def __init__(self, status: str, terminal: bool) -> None:
        self.status = status
        self.terminal = terminal
        self.stage: str | None = status
        self.cancel_requested = False
        self.attempt = 1
        self.stages: list[Any] = []

    def model_dump(self, mode: str = "json") -> dict[str, Any]:
        return {"status": self.status, "terminal": self.terminal}


@pytest.fixture
def client(tenant_world, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """The Reference org's owner, with a stand-in job service (the tests patch the views)."""
    app.dependency_overrides[get_jobs] = lambda: object()
    kariba = tenant_world.project_ids["kariba-redd"]
    monkeypatch.setattr(events, "_project_of", lambda jobs, job_id: kariba)
    return tenant_world.client("ref")


def test_events_stream_changes_then_done(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    views = iter([_View("queued", False), _View("running", False), _View("succeeded", True)])
    monkeypatch.setattr(events, "_view", lambda jobs, job_id: next(views))
    monkeypatch.setattr(events, "POLL_INTERVAL_SECONDS", 0)
    response = client.get("/jobs/abc/events")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    frames = [f for f in response.text.split("\n\n") if f]
    assert [f.splitlines()[0] for f in frames] == [
        "event: progress",
        "event: progress",
        "event: progress",
        "event: done",
    ]
    assert json.loads(frames[-1].splitlines()[1][len("data: ") :])["status"] == "succeeded"


def test_events_unknown_job_is_404(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(events, "_project_of", lambda jobs, job_id: None)
    monkeypatch.setattr(events, "_view", lambda jobs, job_id: None)
    response = client.get("/jobs/nope/events")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "run_not_found"


def test_boundary_geojson_served(client: TestClient) -> None:
    response = client.get("/cases/kariba-redd/boundary.geojson")
    assert response.status_code == 200
    assert response.json()["type"] == "FeatureCollection"


def test_boundary_missing_file_is_404(client: TestClient) -> None:
    response = client.get("/cases/mikoko-pamoja/boundary.geojson")
    assert response.status_code == 404


def test_tile_without_postgis_is_503(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        tiles,
        "get_settings",
        lambda: get_settings().model_copy(update={"database_url": "sqlite:///x.db"}),
    )
    response = client.get("/tiles/3/4/4.mvt")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "postgis_not_configured"
