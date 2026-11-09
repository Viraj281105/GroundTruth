"""The job status, progress, cancel and submit endpoints (issue #37).

SQLite through the real migrations, FastAPI's ``TestClient``, and the real queue and
worker. A fake clock drives every elapsed time, so no test sleeps to "see progress".
Engine results are real output on the synthetic fixture (SIMULATED DATA), replayed by a
stand-in engine where a test needs to control what happens while the engine "runs".
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
import threading
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "tenancy"))
from world import ORIGIN, build_world, configure_auth

from groundtruth.contracts.errors import DataUnavailableError
from groundtruth.contracts.identifiers import new_run_id
from groundtruth.contracts.request import AnalysisRequest
from groundtruth.contracts.result import (
    AnalysisError,
    AnalysisResult,
    EngineStatus,
    ErrorCode,
)
from groundtruth.engine import run_analysis
from groundtruth.platform.api import jobs as jobs_api
from groundtruth.platform.api.app import ERROR_STATUS, app
from groundtruth.platform.api.dependencies import get_jobs, get_store, reset_store
from groundtruth.platform.api.errors import API_ERROR_STATUS, ApiErrorCode
from groundtruth.platform.cases.registry import get_case
from groundtruth.platform.datasets.access import synthetic_access
from groundtruth.platform.jobs.lifecycle import DEFAULT_LEASE, LeaseLostError
from groundtruth.platform.jobs.queue import JobQueue
from groundtruth.platform.jobs.service import SqlJobService
from groundtruth.platform.jobs.worker import Worker, default_resolve_access
from groundtruth.platform.store import database, migrate
from groundtruth.platform.store.database import create_db_engine, create_session_factory
from groundtruth.platform.store.models import AnalysisRunRow, CaseRow, JobRow
from groundtruth.platform.store.sql import SqlEvidenceStore

T0 = datetime(2026, 11, 2, 12, 0, 0, tzinfo=UTC)
WAIT = 30.0
STAGES = ["claim", "data", "engine", "record"]


class FakeClock:
    def __init__(self) -> None:
        self.now = T0
        self._lock = threading.Lock()

    def __call__(self) -> datetime:
        return self.now

    def tick(self, seconds: float = 1.0) -> datetime:
        with self._lock:
            self.now += timedelta(seconds=seconds)
            return self.now


def _request(*, seed: int = 20260101, min_donors: int | None = None) -> AnalysisRequest:
    return get_case("kariba-redd").to_request(seed=seed, min_donors=min_donors)


@pytest.fixture(scope="module")
def completed() -> AnalysisResult:
    """A real completed run on SIMULATED DATA, for the default request."""
    request = _request()
    result = run_analysis(request, synthetic_access(request, true_effect=0.06))
    assert result.status is EngineStatus.COMPLETED
    return result


@pytest.fixture(scope="module")
def refused() -> AnalysisResult:
    """A real refusal: no donor pool of 500 exists. Its request is ``min_donors=500``."""
    request = _request(min_donors=500)
    result = run_analysis(request, synthetic_access(request, true_effect=0.06))
    assert result.status is EngineStatus.REFUSED
    return result


class Engine:
    """A stand-in for ``run_analysis``: acts, replays a prepared result, counts calls."""

    def __init__(self, result: AnalysisResult | Exception, *, before=None, wait_for=None) -> None:
        self.result, self.before, self.wait_for, self.calls = result, before, wait_for, 0

    def __call__(self, request: AnalysisRequest, data: Any) -> AnalysisResult:
        self.calls += 1
        if self.before is not None:
            self.before()
        if self.wait_for is not None:
            assert self.wait_for.wait(WAIT), "the engine stand-in waited too long"
        if isinstance(self.result, Exception):
            raise self.result
        return self.result.model_copy(update={"run_id": new_run_id()})


class SpyQueue(JobQueue):
    """A real queue that signals when a heartbeat has seen a cancel request."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.cancel_seen = threading.Event()

    def heartbeat(self, job):
        cancel = super().heartbeat(job)
        if cancel:
            self.cancel_seen.set()
        return cancel


@pytest.fixture(autouse=True)
def _pin_settings_and_cache(monkeypatch):
    """The API reads the seed from settings; pin it so the specification is known."""
    monkeypatch.setattr(jobs_api, "get_settings", lambda: SimpleNamespace(random_seed=20260101))
    reset_store()
    yield
    reset_store()
    app.dependency_overrides.clear()


@pytest.fixture
def url(tmp_path: pathlib.Path) -> str:
    return f"sqlite:///{tmp_path / 'jobs.db'}"


@pytest.fixture
def sessions(url: str) -> sessionmaker[Session]:
    migrate.upgrade(url)
    return create_session_factory(create_db_engine(url, connect_args={"timeout": 30}))


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def store(sessions, clock) -> SqlEvidenceStore:
    store = SqlEvidenceStore(sessions, clock=clock)
    store.upsert_case(get_case("kariba-redd"))
    return store


@pytest.fixture
def queue(sessions, clock, store) -> SpyQueue:
    return SpyQueue(sessions, clock=clock)


@pytest.fixture
def signed_in(sessions, monkeypatch):
    """The Reference org's owner, signed in on this test's database.

    Every job route is project-scoped now, so the routes under test are driven by the user who
    owns the case's project. Call it after ``get_store`` is overridden (sign-in goes through
    the app). Runs the tests create straight through the queue are filed under their case's
    project before each request, as the seed's backfill would on a seeded database.
    """
    configure_auth(monkeypatch)
    cache: list[TestClient] = []

    def get() -> TestClient:
        if not cache:
            root = TestClient(app, base_url=ORIGIN)
            world = build_world(root, sessions, wire_jobs=False, backfill=True)
            cache.append(world.client("ref"))
        return cache[0]

    return get


@pytest.fixture
def make_client(store, signed_in):
    """A signed-in client whose job service runs on the given queue."""

    def make(queue: JobQueue) -> TestClient:
        app.dependency_overrides[get_store] = lambda: store
        app.dependency_overrides[get_jobs] = lambda: SqlJobService(store, queue)
        return signed_in()

    return make


@pytest.fixture
def client(make_client, queue) -> TestClient:
    return make_client(queue)


def _worker(queue: JobQueue, **kwargs) -> Worker:
    kwargs.setdefault("worker_id", "w-secret-host-4242")
    kwargs.setdefault("heartbeat_interval", 0.01)
    return Worker(queue, **kwargs)


def _get(client: TestClient, run_id: str) -> dict[str, Any]:
    response = client.get(f"/jobs/{run_id}")
    assert response.status_code == 200, response.text
    return response.json()


def _states(body: dict[str, Any]) -> dict[str, str]:
    return {s["name"]: s["state"] for s in body["stages"]}


def _stage(body: dict[str, Any], name: str) -> dict[str, Any]:
    return next(s for s in body["stages"] if s["name"] == name)


def _error(response) -> dict[str, Any]:
    return response.json()["detail"]


def _keys(node: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            found.add(key)
            found |= _keys(value)
    elif isinstance(node, list):
        for value in node:
            found |= _keys(value)
    return found


def _run_to_completion(queue, result, request) -> str:
    """Submit ``request``, run it on a worker whose engine returns ``result``."""
    run_id = queue.submit(request).run_id
    _worker(queue, run=Engine(result), resolve_access=lambda r: None).run(exit_when_idle=True)
    return run_id


# --- submitting -----------------------------------------------------------------


class TestSubmit:
    def _submit(self, client, **body):
        return client.post("/jobs", json={"case_id": "kariba-redd", **body})

    def test_a_new_job_is_queued_and_returned_at_once(self, client):
        response = self._submit(client)
        body = response.json()

        assert response.status_code == 202
        assert response.headers["cache-control"] == "no-store"
        assert body["from_cache"] is False and body["deduplicated"] is False
        assert body["status_url"] == f"/jobs/{body['run_id']}"
        job = body["job"]
        assert (job["status"], job["result_state"], job["terminal"]) == ("queued", "queued", False)
        assert job["run_id"] == body["run_id"] and job["case_id"] == "kariba-redd"

    def test_it_is_labelled_simulated_everywhere(self, client):
        job = self._submit(client).json()["job"]
        assert job["data_mode"] == "simulated" and job["is_simulated"] is True
        assert job["notice"].startswith("SIMULATED DATA")

    def test_the_request_is_the_cases_with_the_configured_seed(self, client, sessions):
        run_id = self._submit(client, min_donors=7).json()["run_id"]
        expected = _request(min_donors=7)
        with sessions() as session:
            run = session.get(AnalysisRunRow, run_id)
            assert (run.spec_hash, run.seed, run.data_mode) == (
                expected.spec_hash, 20260101, "simulated",
            )  # fmt: skip

    def test_the_case_is_stored_first_when_it_was_not(self, sessions, clock, signed_in):
        bare = SqlEvidenceStore(sessions, clock=clock)  # no upsert_case
        queue = JobQueue(sessions, clock=clock)
        app.dependency_overrides[get_store] = lambda: bare
        app.dependency_overrides[get_jobs] = lambda: SqlJobService(bare, queue)
        with sessions() as session:
            assert session.get(CaseRow, "kariba-redd") is None

        response = self._submit(signed_in())

        assert response.status_code == 202
        with sessions() as session:
            assert session.get(CaseRow, "kariba-redd") is not None

    def test_an_identical_request_in_flight_is_the_same_job(self, client, sessions):
        first = self._submit(client).json()
        again = self._submit(client)
        assert again.status_code == 200  # nothing new was queued
        assert again.json()["deduplicated"] is True
        assert again.json()["run_id"] == first["run_id"]
        with sessions() as session:
            assert session.scalar(sa.select(sa.func.count()).select_from(JobRow)) == 1

    def test_a_stored_result_answers_without_queueing_anything(
        self, client, queue, sessions, completed
    ):
        first = self._submit(client).json()
        _worker(queue, run=Engine(completed), resolve_access=lambda r: None).run(
            exit_when_idle=True
        )

        again = self._submit(client)
        body = again.json()

        assert again.status_code == 200
        assert body["from_cache"] is True and body["run_id"] == first["run_id"]
        assert body["job"]["result_state"] == "measured" and body["job"]["is_simulated"] is True
        assert body["job"]["notice"].startswith("SIMULATED DATA")  # a cache hit is labelled too
        with sessions() as session:
            assert session.scalar(sa.select(sa.func.count()).select_from(JobRow)) == 1

    def test_a_cancelled_job_does_not_block_a_new_one(self, client):
        first = self._submit(client).json()["run_id"]
        client.post(f"/jobs/{first}/cancel")
        second = self._submit(client)
        assert second.status_code == 202 and second.json()["run_id"] != first

    def test_a_different_donor_floor_is_a_different_job(self, client):
        a, b = self._submit(client).json(), self._submit(client, min_donors=11).json()
        assert a["run_id"] != b["run_id"]

    def test_observed_data_is_refused_not_simulated(self, client, sessions):
        response = self._submit(client, synthetic=False)
        assert response.status_code == 501
        assert _error(response)["code"] == "not_implemented"
        with sessions() as session:
            assert session.scalar(sa.select(sa.func.count()).select_from(AnalysisRunRow)) == 0

    def test_an_unknown_case_is_a_404_and_queues_nothing(self, client, sessions):
        response = client.post("/jobs", json={"case_id": "no-such-case"})
        assert response.status_code == 404 and _error(response)["code"] == "case_not_found"
        with sessions() as session:
            assert session.scalar(sa.select(sa.func.count()).select_from(AnalysisRunRow)) == 0

    @pytest.mark.parametrize(
        "body",
        [
            {},
            {"case_id": "kariba-redd", "min_donors": 1},
            {"case_id": "kariba-redd", "true_effect": 0.5},
            {"case_id": "kariba-redd", "requested_by": "someone"},
            {"case_id": "kariba-redd", "synthetic": "maybe"},
        ],
        ids=["no-case", "floor-too-low", "true-effect", "unknown-field", "bad-bool"],
    )
    def test_a_bad_body_is_a_422(self, client, body):
        """``true_effect`` is refused, not ignored: it is not part of the specification hash."""
        assert client.post("/jobs", json=body).status_code == 422


# --- status ---------------------------------------------------------------------


class TestStatus:
    def test_an_unknown_job_is_a_404(self, client):
        response = client.get("/jobs/run_0000000000000000")
        assert response.status_code == 404 and _error(response)["code"] == "run_not_found"

    def test_a_status_is_never_cached(self, client, queue):
        run_id = queue.submit(_request()).run_id
        assert client.get(f"/jobs/{run_id}").headers["cache-control"] == "no-store"

    def test_a_queued_job_has_planned_stages_and_nothing_else(self, client, queue):
        run_id = queue.submit(_request()).run_id
        body = _get(client, run_id)

        assert (body["status"], body["result_state"], body["terminal"]) == (
            "queued", "queued", False,
        )  # fmt: skip
        assert body["stage"] is None and set(_states(body).values()) == {"pending"}
        assert [e["event"] for e in body["timeline"]] == ["queued"]
        assert body["engine_metrics"]["available"] is False
        assert (body["attempt"], body["cancel_requested"], body["retry_at"]) == (0, False, None)
        assert body["result_url"] is None and body["error"] is None
        assert body["status_url"] == f"/jobs/{run_id}"

    def test_each_stage_is_visible_as_it_begins_with_its_real_times(
        self, client, queue, clock, completed
    ):
        run_id = queue.submit(_request()).run_id
        clock.tick(10)  # waits in the queue
        job = queue.claim("w1")

        body = _get(client, run_id)
        assert body["status"] == "running" and body["stage"] == "claim"
        assert _states(body) == {
            "claim": "active", "data": "pending", "engine": "pending", "record": "pending",
        }  # fmt: skip
        assert _stage(body, "claim")["elapsed_ms"] == 0
        assert [e["event"] for e in body["timeline"]] == ["queued", "running"]
        assert body["last_heartbeat_at"] is not None and body["lease_expires_at"] is not None

        clock.tick(2)
        queue.checkpoint(job, "before-data", begins="data")
        body = _get(client, run_id)
        assert body["stage"] == "data" and _states(body)["claim"] == "done"
        assert _stage(body, "claim")["duration_ms"] == 2000

        clock.tick(3)
        queue.checkpoint(job, "before-engine", begins="engine")
        clock.tick(4)  # the engine has been running for four seconds
        body = _get(client, run_id)
        assert body["stage"] == "engine"
        assert _stage(body, "data")["duration_ms"] == 3000
        assert _stage(body, "engine")["state"] == "active"
        assert _stage(body, "engine")["elapsed_ms"] == 4000
        assert _stage(body, "record")["state"] == "pending"
        # While the engine runs its own timings are not known, and are not invented.
        assert body["engine_metrics"]["available"] is False
        assert body["engine_metrics"]["stages"] == [] and body["engine_metrics"]["total_ms"] is None

        assert queue.complete(job, completed).value == "succeeded"
        body = _get(client, run_id)
        assert set(_states(body).values()) == {"done"}
        assert body["terminal"] is True and body["last_heartbeat_at"] is None
        assert [e["event"] for e in body["timeline"]] == ["queued", "running", "succeeded"]

    def test_the_recording_stage_claims_no_duration(self, client, queue, completed):
        """It begins and ends in one transaction; a duration of zero would be false."""
        run_id = _run_to_completion(queue, completed, _request())
        record = _stage(_get(client, run_id), "record")
        assert record["state"] == "done" and record["duration_ms"] is None

    def test_there_is_no_percentage_anywhere(self, client, queue, completed, refused):
        done = _run_to_completion(queue, completed, _request())
        refusal = _run_to_completion(queue, refused, _request(min_donors=500))
        waiting = queue.submit(_request(seed=5)).run_id
        for run_id in (done, refusal, waiting):
            body = _get(client, run_id)
            assert not [k for k in _keys(body) if re.search(r"percent|pct|fraction|remaining", k)]
            assert "no percentage" in body["note"]

    def test_the_engines_own_stages_come_from_run_metrics_after_it_finishes(
        self, client, queue, completed
    ):
        run_id = _run_to_completion(queue, completed, _request())
        metrics = _get(client, run_id)["engine_metrics"]

        assert metrics["available"] is True and metrics["source"] == "run_metrics"
        assert [s["name"] for s in metrics["stages"]] == list(completed.metrics.stage_durations_ms)
        assert {s["name"] for s in metrics["stages"]} >= {
            "observation", "matching", "alignment", "estimation", "robustness", "assembly",
        }  # fmt: skip
        assert (
            metrics["stages"][0]["duration_ms"]
            == completed.metrics.stage_durations_ms[metrics["stages"][0]["name"]]
        )
        assert metrics["total_ms"] == completed.metrics.duration_ms
        assert metrics["n_donors_admitted"] == completed.metrics.n_donors_admitted
        assert metrics["n_estimator_fits"] == completed.metrics.n_estimator_fits
        assert metrics["stopped_at"] is None

    def test_a_refusal_is_a_completed_job_not_a_failure(self, client, queue, refused):
        run_id = _run_to_completion(queue, refused, _request(min_donors=500))
        body = _get(client, run_id)

        assert body["status"] == "succeeded"
        assert body["status"] != "failed" and body["result_state"] != "failed"
        assert (body["result_state"], body["engine_status"], body["terminal"]) == (
            "refused", "refused", True,
        )  # fmt: skip
        assert body["error"]["is_refusal"] is True
        assert body["error"]["code"] == "donor_pool_inadequate" and body["error"]["remediation"]
        assert set(_states(body).values()) == {"done"}  # every stage of the job completed
        assert body["result_url"] == f"/runs/{run_id}" and body["failure_reason"] is None

    def test_a_refusal_shows_what_the_engine_reported_and_invents_no_stages(
        self, client, queue, refused
    ):
        """The engine gives a refusal's total time, counts and where it stopped, but no
        per-stage timings (it fills those in only for a completed run). None are made up."""
        run_id = _run_to_completion(queue, refused, _request(min_donors=500))
        metrics = _get(client, run_id)["engine_metrics"]

        assert refused.metrics.stage_durations_ms == {}  # the premise: the engine reports none
        assert metrics["available"] is True and metrics["stages"] == []
        assert metrics["total_ms"] == refused.metrics.duration_ms > 0
        assert metrics["stopped_at"] == refused.error.stage == "matching"
        assert metrics["n_donors_admitted"] == 0 and metrics["n_estimator_fits"] == 0
        assert "only for a completed analysis" in metrics["note"]

    def test_the_job_and_the_run_always_agree_on_the_state(self, client, queue, completed, refused):
        """Both endpoints derive ``result_state`` from one function; check they match."""
        runs = {
            _run_to_completion(queue, completed, _request()),
            _run_to_completion(queue, refused, _request(min_donors=500)),
            queue.submit(_request(seed=41)).run_id,
        }
        cancelled = queue.submit(_request(seed=42)).run_id
        queue.cancel(cancelled)
        runs.add(cancelled)
        assert {"measured", "refused", "queued", "cancelled"} == {
            _get(client, r)["result_state"] for r in runs
        }
        for run_id in runs:
            assert (
                _get(client, run_id)["result_state"]
                == client.get(f"/runs/{run_id}").json()["result_state"]
            )

    def test_an_engine_error_is_failed_and_not_a_refusal(self, client, queue, completed):
        bad = completed.model_copy(
            update={
                "status": EngineStatus.ERROR,
                "bundle": None,
                "error": AnalysisError(code=ErrorCode.ESTIMATION_FAILED, message="no fit"),
            }
        )
        run_id = _run_to_completion(queue, bad, _request())
        body = _get(client, run_id)
        assert (body["status"], body["result_state"]) == ("failed", "failed")
        assert body["error"]["is_refusal"] is False and body["terminal"] is True
        assert set(_states(body).values()) == {"done"}  # the stages ran; the engine errored

    def test_a_job_that_failed_before_the_engine_says_where_and_why(self, client, queue, sessions):
        run_id = queue.submit(_request()).run_id
        with sessions.begin() as session:
            session.get(AnalysisRunRow, run_id).request = None  # unusable stored request
        assert queue.claim("w1") is None

        body = _get(client, run_id)
        assert (body["status"], body["failure_reason"]) == ("failed", "unusable-request")
        assert _states(body) == {
            "claim": "failed", "data": "skipped", "engine": "skipped", "record": "skipped",
        }  # fmt: skip
        assert body["error"] is None

    def test_a_failure_while_resolving_data_marks_that_stage(
        self, make_client, sessions, clock, store
    ):
        queue = SpyQueue(sessions, clock=clock, max_attempts=1)
        client = make_client(queue)
        run_id = queue.submit(_request()).run_id

        def no_data(request):
            raise DataUnavailableError("upstream outage")

        _worker(queue, resolve_access=no_data).run(exit_when_idle=True)
        body = _get(client, run_id)

        assert body["status"] == "failed" and "upstream outage" in body["failure_reason"]
        assert _states(body) == {
            "claim": "done", "data": "failed", "engine": "skipped", "record": "skipped",
        }  # fmt: skip

    def test_a_retry_starts_from_a_clean_slate(self, client, queue, clock, completed):
        bad = completed.model_copy(
            update={
                "status": EngineStatus.ERROR,
                "bundle": None,
                "error": AnalysisError(code=ErrorCode.DATA_UNAVAILABLE, message="upstream"),
            }
        )
        run_id = queue.submit(_request()).run_id
        _worker(queue, run=Engine(bad), resolve_access=lambda r: None).run(max_jobs=1)

        body = _get(client, run_id)
        assert (body["status"], body["attempt"]) == ("queued", 1)
        assert body["stage"] is None and set(_states(body).values()) == {"pending"}
        assert body["retry_at"] == (clock.now + timedelta(seconds=30)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        assert body["engine_metrics"]["available"] is False and body["terminal"] is False

    def test_a_job_cancelled_while_queued_never_reached_any_stage(self, client, queue):
        run_id = queue.submit(_request()).run_id
        queue.cancel(run_id)
        body = _get(client, run_id)
        assert set(_states(body).values()) == {"skipped"}
        assert [e["event"] for e in body["timeline"]] == ["queued", "cancelled"]

    def test_a_job_cancelled_between_stages_shows_what_it_reached(self, client, queue):
        run_id = queue.submit(_request()).run_id

        def cancel_while_resolving(request):
            client.post(f"/jobs/{run_id}/cancel")
            return None

        _worker(queue, resolve_access=cancel_while_resolving).run(exit_when_idle=True)
        body = _get(client, run_id)

        assert body["status"] == "cancelled" and body["result_state"] == "cancelled"
        assert _states(body) == {
            "claim": "done", "data": "done", "engine": "skipped", "record": "skipped",
        }  # fmt: skip

    def test_a_job_with_no_recorded_stages_is_unknown_not_guessed(self, client, queue, sessions):
        """A row from before stages were recorded: say so, do not invent a position."""
        run_id = queue.submit(_request()).run_id
        queue.claim("w1")
        with sessions.begin() as session:
            row = session.get(JobRow, run_id)
            row.stage, row.stage_log = None, None
        body = _get(client, run_id)
        assert body["status"] == "running" and body["stage"] is None
        assert set(_states(body).values()) == {"unknown"}

    def test_a_result_saved_without_a_job_is_still_reported(self, client, store, clock, completed):
        clock.tick()
        store.save_result(completed.model_copy(update={"run_id": "run_00000000000000ff"}))
        body = _get(client, "run_00000000000000ff")
        assert (body["status"], body["result_state"], body["attempt"]) == (
            "succeeded",
            "measured",
            None,
        )
        assert set(_states(body).values()) == {"unknown"} and body["terminal"] is True

    def test_the_worker_is_not_identified(self, client, queue, completed):
        run_id = queue.submit(_request()).run_id
        queue.claim("w-secret-host-4242")
        text = json.dumps(_get(client, run_id))
        assert "w-secret-host-4242" not in text
        assert not {"locked_by", "worker", "worker_id"} & _keys(json.loads(text))


# --- watching a job as it happens -----------------------------------------------


class TestLiveObservation:
    def test_the_status_changes_are_observable_from_inside_the_worker(
        self, client, queue, clock, completed
    ):
        """The worker's own stage hooks poll the API, so each moment is seen deterministically."""
        run_id = queue.submit(_request()).run_id
        seen: list[tuple[str, str | None, dict[str, str]]] = []

        def look(note: str = "") -> None:
            body = _get(client, run_id)
            seen.append((body["status"], body["stage"], _states(body)))

        seen.append(("before", None, {}))
        look()  # queued, before any worker exists

        def resolve(request):
            look()
            return None

        def engine_runs():
            look()
            clock.tick(3)
            look()

        worker = _worker(queue, resolve_access=resolve, run=Engine(completed, before=engine_runs))
        worker.run(exit_when_idle=True)
        look()

        sequence = [(status, stage) for _, (status, stage, _) in enumerate(seen[1:], 1)]
        assert sequence == [
            ("queued", None),
            ("running", "data"),
            ("running", "engine"),
            ("running", "engine"),
            ("succeeded", "record"),
        ]
        # while the engine ran, its stage was the active one, and time was passing in it
        assert seen[3][2]["engine"] == "active" and seen[3][2]["record"] == "pending"
        final = _get(client, run_id)
        assert _stage(final, "engine")["duration_ms"] == 3000

    def test_the_timeline_lists_the_job_level_transitions_in_order(
        self, client, queue, clock, completed
    ):
        run_id = queue.submit(_request()).run_id
        clock.tick(5)
        _worker(queue, run=Engine(completed, before=lambda: clock.tick(2)),
                resolve_access=lambda r: None).run(exit_when_idle=True)  # fmt: skip
        timeline = _get(client, run_id)["timeline"]
        assert [e["event"] for e in timeline] == ["queued", "running", "succeeded"]
        times = [e["at"] for e in timeline]
        assert times == sorted(times) and times[0] != times[1]


# --- cancelling -----------------------------------------------------------------


class TestCancel:
    def test_a_queued_job_is_cancelled_at_once_with_a_200(self, client, queue):
        run_id = queue.submit(_request()).run_id
        response = client.post(f"/jobs/{run_id}/cancel")
        body = response.json()

        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert (body["status"], body["result_state"], body["terminal"]) == (
            "cancelled", "cancelled", True,
        )  # fmt: skip
        assert body["cancel_requested"] is True
        assert queue.claim("w1") is None  # no worker will ever start it

    def test_a_running_job_is_a_202_that_is_requested_not_yet_done(self, client, queue):
        run_id = queue.submit(_request()).run_id
        queue.claim("w1")
        response = client.post(f"/jobs/{run_id}/cancel")
        body = response.json()

        assert response.status_code == 202
        assert (body["status"], body["terminal"], body["cancel_requested"]) == (
            "running",
            False,
            True,
        )

    def test_asking_twice_is_harmless(self, client, queue):
        running = queue.submit(_request(seed=1)).run_id
        queue.claim("w1")
        queued = queue.submit(_request(seed=2)).run_id
        assert [client.post(f"/jobs/{running}/cancel").status_code for _ in range(2)] == [202, 202]
        assert [client.post(f"/jobs/{queued}/cancel").status_code for _ in range(2)] == [200, 200]

    def test_the_worker_honours_a_cancel_made_through_the_api_while_the_engine_runs(
        self, make_client, sessions, clock, store, completed
    ):
        queue = SpyQueue(sessions, clock=clock)
        client = make_client(queue)
        run_id = queue.submit(_request()).run_id
        responses: list[int] = []
        engine = Engine(
            completed,
            before=lambda: responses.append(client.post(f"/jobs/{run_id}/cancel").status_code),
            wait_for=queue.cancel_seen,  # the heartbeat must notice before the engine returns
        )

        _worker(queue, run=engine, resolve_access=lambda r: None).run(exit_when_idle=True)

        assert responses == [202]  # it was running when asked
        body = _get(client, run_id)
        assert (body["status"], body["result_state"], body["terminal"]) == (
            "cancelled", "cancelled", True,
        )  # fmt: skip
        assert body["engine_status"] is None  # the engine ran, but its result was discarded
        assert store.by_run_id(run_id) is None  # the engine's result was discarded
        assert client.get(f"/runs/{run_id}").json()["has_bundle"] is False

    @pytest.mark.parametrize("outcome", ["succeeded", "refused", "failed"])
    def test_a_finished_job_is_a_409_and_is_left_alone(
        self, client, queue, completed, refused, outcome
    ):
        if outcome == "succeeded":
            run_id = _run_to_completion(queue, completed, _request())
        elif outcome == "refused":
            run_id = _run_to_completion(queue, refused, _request(min_donors=500))
        else:
            bad = completed.model_copy(update={
                "status": EngineStatus.ERROR, "bundle": None,
                "error": AnalysisError(code=ErrorCode.ESTIMATION_FAILED, message="x"),
            })  # fmt: skip
            run_id = _run_to_completion(queue, bad, _request())
        before = _get(client, run_id)

        response = client.post(f"/jobs/{run_id}/cancel")

        assert response.status_code == 409
        assert _error(response)["code"] == "job_already_finished"
        assert before["status"] in _error(response)["message"]
        assert _get(client, run_id) == before  # nothing changed

    def test_an_unknown_job_is_a_404(self, client):
        response = client.post("/jobs/run_0000000000000000/cancel")
        assert response.status_code == 404 and _error(response)["code"] == "run_not_found"

    def test_a_cancelled_job_stays_visible_to_the_run_listing(self, client, queue):
        run_id = queue.submit(_request()).run_id
        client.post(f"/jobs/{run_id}/cancel")
        listed = client.get("/runs", params={"status": "cancelled"}).json()["items"]
        assert [i["run_id"] for i in listed] == [run_id]


# --- the whole path, with the real engine ---------------------------------------


class TestEndToEnd:
    def test_submit_run_and_watch_kariba_through_the_api(self, client, queue):
        """POST, a real worker with the real engine, then GET: all on SIMULATED DATA."""
        run_id = client.post("/jobs", json={"case_id": "kariba-redd"}).json()["run_id"]
        assert _get(client, run_id)["status"] == "queued"

        _worker(queue, resolve_access=default_resolve_access()).run(exit_when_idle=True)
        body = _get(client, run_id)

        assert (body["status"], body["result_state"], body["terminal"]) == (
            "succeeded", "measured", True,
        )  # fmt: skip
        assert body["is_simulated"] is True and set(_states(body).values()) == {"done"}
        metrics = body["engine_metrics"]
        assert metrics["available"] is True and len(metrics["stages"]) >= 5
        assert metrics["total_ms"] > 0 and metrics["n_donors_admitted"] > 0
        result = client.get(body["result_url"]).json()
        assert result["result_state"] == "measured" and len(result["bundle"]["items"]) > 10

        again = client.post("/jobs", json={"case_id": "kariba-redd"})
        assert again.status_code == 200 and again.json()["from_cache"] is True

    def test_a_real_refusal_reports_as_completed(self, client, queue):
        run_id = client.post("/jobs", json={"case_id": "kariba-redd", "min_donors": 500}).json()[
            "run_id"
        ]
        _worker(queue, resolve_access=default_resolve_access()).run(exit_when_idle=True)
        body = _get(client, run_id)

        assert (body["status"], body["result_state"]) == ("succeeded", "refused")
        assert body["error"]["is_refusal"] is True and body["engine_metrics"]["available"] is True
        assert "assembly" not in [s["name"] for s in body["engine_metrics"]["stages"]]


# --- recording stages (the queue) -----------------------------------------------


class TestStageRecording:
    def test_claim_records_the_first_stage(self, queue, sessions, clock):
        run_id = queue.submit(_request()).run_id
        queue.claim("w1")
        with sessions() as session:
            row = session.get(JobRow, run_id)
            assert row.stage == "claim" and row.stage_log == {"claim": clock.now.isoformat()}

    def test_a_cancelled_checkpoint_does_not_record_a_stage_that_never_began(self, queue, sessions):
        run_id = queue.submit(_request()).run_id
        job = queue.claim("w1")
        queue.cancel(run_id)
        from groundtruth.platform.jobs.lifecycle import JobCancelledError

        with pytest.raises(JobCancelledError):
            queue.checkpoint(job, "before-data", begins="data")
        with sessions() as session:
            assert session.get(JobRow, run_id).stage_log == {"claim": T0.isoformat()}

    def test_a_worker_that_lost_its_lease_cannot_write_a_stage(self, queue, sessions, clock):
        run_id = queue.submit(_request()).run_id
        zombie = queue.claim("w1")
        clock.tick(DEFAULT_LEASE.total_seconds() + 1)
        queue.reap_expired()
        clock.tick(31)
        queue.claim("w2")

        with pytest.raises(LeaseLostError):
            queue.checkpoint(zombie, "before-data", begins="data")
        with sessions() as session:
            assert session.get(JobRow, run_id).stage == "claim"  # the new attempt's, untouched

    def test_complete_records_the_record_stage_with_the_result(self, queue, sessions, completed):
        run_id = queue.submit(_request()).run_id
        job = queue.claim("w1")
        queue.complete(job, completed)
        with sessions() as session:
            row = session.get(JobRow, run_id)
            assert row.stage == "record" and set(row.stage_log) == {"claim", "record"}


# --- when there is no database --------------------------------------------------


class TestUnavailable:
    def _plain(self) -> TestClient:
        app.dependency_overrides.clear()
        return TestClient(app)

    def test_without_a_database_every_job_endpoint_answers_503(self, monkeypatch):
        monkeypatch.setattr(database, "get_settings", lambda: SimpleNamespace(database_url=None))
        client = self._plain()
        calls = [
            client.post("/jobs", json={"case_id": "kariba-redd"}),
            client.get("/jobs/run_0000000000000000"),
            client.post("/jobs/run_0000000000000000/cancel"),
        ]
        for response in calls:
            assert response.status_code == 503
            assert _error(response)["code"] == "store_not_configured"
            assert "DATABASE_URL" in _error(response)["hint"]

    def test_the_other_endpoints_do_not_notice(self, monkeypatch):
        monkeypatch.setattr(database, "get_settings", lambda: SimpleNamespace(database_url=None))
        client = self._plain()
        assert client.get("/health").status_code == 200
        # Project-scoped now: with no session they answer 401 by themselves, never a 503.
        assert client.get("/cases").status_code == 401
        assert client.get("/cases/kariba-redd").status_code == 401
        assert client.get("/runs").status_code == 503  # unchanged from issue #35

    def test_a_database_that_stops_answering_is_a_503(self, store, signed_in):
        class Dying:
            def _down(self):
                raise sa.exc.OperationalError("SELECT", {}, Exception("connection reset"))

            def status(self, run_id):
                self._down()

            def cancel(self, run_id):
                self._down()

            def submit(self, case, request, **_):
                self._down()

        app.dependency_overrides[get_store] = lambda: store
        client = signed_in()  # sign-in works; only the job service is down
        app.dependency_overrides[get_jobs] = lambda: Dying()
        for response in (
            client.get("/jobs/run_0000000000000000"),
            client.post("/jobs/run_0000000000000000/cancel"),
            client.post("/jobs", json={"case_id": "kariba-redd"}),
        ):
            assert response.status_code == 503
            assert _error(response)["code"] == "store_unavailable"

    def test_a_schema_behind_the_migrations_is_a_503_with_the_fix(self, monkeypatch, url):
        monkeypatch.setattr(database, "get_settings", lambda: SimpleNamespace(database_url=url))
        response = self._plain().get("/jobs/run_0000000000000000")
        assert response.status_code == 503 and "--migrate" in _error(response)["hint"]


# --- schema and migration -------------------------------------------------------


class TestSchemaAndMigration:
    def test_the_openapi_schema_lists_the_job_endpoints_and_keeps_the_old_ones(self):
        schema = TestClient(app).get("/openapi.json").json()
        assert {"/jobs", "/jobs/{run_id}", "/jobs/{run_id}/cancel"} <= set(schema["paths"])
        assert {
            "/health", "/cases", "/cases/{case_id}", "/cases/{case_id}/verify",
            "/runs", "/runs/{run_id}", "/runs/compare",
        } <= set(schema["paths"])  # fmt: skip
        for name in ("JobView", "JobSubmission", "SubmitJobRequest", "StageView",
                     "EngineMetricsView"):  # fmt: skip
            assert name in schema["components"]["schemas"], name

    def test_the_new_error_codes_have_the_right_statuses(self):
        assert set(ApiErrorCode) == set(API_ERROR_STATUS)
        assert API_ERROR_STATUS[ApiErrorCode.JOB_ALREADY_FINISHED] == 409
        assert API_ERROR_STATUS[ApiErrorCode.CASE_NOT_FOUND] == 404
        assert (
            API_ERROR_STATUS[ApiErrorCode.NOT_IMPLEMENTED]
            == ERROR_STATUS[ErrorCode.NOT_IMPLEMENTED]
        )
        assert ApiErrorCode.NOT_IMPLEMENTED.value == ErrorCode.NOT_IMPLEMENTED.value

    def test_the_stage_names_are_the_ones_the_worker_logs(self):
        from groundtruth.platform.jobs.interface import LIVE_STAGES

        assert list(LIVE_STAGES) == STAGES

    def test_migration_0005_adds_and_removes_only_its_columns(self, tmp_path):
        url = f"sqlite:///{tmp_path / 'm.db'}"

        def columns() -> set[str]:
            return {c["name"] for c in sa.inspect(create_db_engine(url)).get_columns("jobs")}

        migrate.upgrade(url)
        assert {"stage", "stage_log"} <= columns()
        migrate.downgrade(url, "0004")
        assert not {"stage", "stage_log"} & columns()
        assert {"lease_expires_at", "attempts"} <= columns()
        migrate.upgrade(url)
        assert {"stage", "stage_log"} <= columns()
