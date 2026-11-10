"""The stored-run endpoints: list, fetch, compare (issue #35).

SQLite through the real migrations and FastAPI's ``TestClient``. Runs are real engine
output on the synthetic fixture (SIMULATED DATA), saved through the real store with a fake
clock, so ordering, ties and "newest" are under the test's control and no test sleeps.
"""

from __future__ import annotations

import base64
import json
import pathlib
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
from world import ORIGIN, build_world, configure_auth, register

from groundtruth.contracts.identifiers import EngineRef, new_run_id
from groundtruth.contracts.result import (
    AnalysisError,
    AnalysisResult,
    EngineStatus,
    ErrorCode,
)
from groundtruth.contracts.types import VerdictLabel
from groundtruth.contracts.version import CONTRACT_VERSION
from groundtruth.engine import ENGINE_VERSION, run_analysis
from groundtruth.platform.api import dependencies
from groundtruth.platform.api.app import ERROR_STATUS, app
from groundtruth.platform.api.cursor import filters_fingerprint
from groundtruth.platform.api.dependencies import get_store, reset_store
from groundtruth.platform.api.errors import API_ERROR_STATUS, ApiErrorCode
from groundtruth.platform.cases.registry import get_case
from groundtruth.platform.datasets.access import synthetic_access
from groundtruth.platform.jobs.queue import JobQueue
from groundtruth.platform.reports.narrative import render_deterministic
from groundtruth.platform.store import database, migrate
from groundtruth.platform.store.database import create_db_engine, create_session_factory
from groundtruth.platform.store.interface import RunFilter, StoreError
from groundtruth.platform.store.models import AnalysisRunRow, JobRow
from groundtruth.platform.store.sql import SqlEvidenceStore

T0 = datetime(2026, 11, 1, 12, 0, 0, tzinfo=UTC)


def iso(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


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


def _request(seed: int = 20260101):
    return get_case("kariba-redd").to_request(seed=seed)


@pytest.fixture(scope="module")
def completed() -> AnalysisResult:
    """A real completed run on SIMULATED DATA."""
    request = _request()
    result = run_analysis(request, synthetic_access(request, true_effect=0.06))
    assert result.status is EngineStatus.COMPLETED
    return result


@pytest.fixture(scope="module")
def refused() -> AnalysisResult:
    """A real refusal: no donor pool of 500 exists."""
    request = get_case("kariba-redd").to_request(seed=20260101, min_donors=500)
    result = run_analysis(request, synthetic_access(request, true_effect=0.06))
    assert result.status is EngineStatus.REFUSED
    return result


@pytest.fixture
def url(tmp_path: pathlib.Path) -> str:
    return f"sqlite:///{tmp_path / 'runs.db'}"


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
    store.upsert_case(get_case("southern-cardamom-redd"))
    return store


@pytest.fixture
def queue(sessions, clock, store) -> JobQueue:
    return JobQueue(sessions, clock=clock)


@pytest.fixture
def client(store, sessions, monkeypatch):
    """The Reference org's owner, signed in: every run route is project-scoped now.

    Runs these tests create through the store and queue are filed under their case's project
    before each request (the seed's backfill), as they would be on a seeded database.
    """
    configure_auth(monkeypatch)
    app.dependency_overrides[get_store] = lambda: store
    with TestClient(app, base_url=ORIGIN) as root:
        yield build_world(root, sessions, wire_jobs=False, backfill=True).client("ref")
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _fresh_store_cache():
    reset_store()
    yield
    reset_store()


def _save(
    store, clock, result, *, advance: float = 1.0, run_id: str | None = None, **changes
) -> str:
    """Save a re-run of ``result`` (new run id, any changed fields) one tick later."""
    clock.tick(advance)
    run_id = run_id or new_run_id()
    store.save_result(result.model_copy(update={"run_id": run_id, **changes}))
    return run_id


def _get(client: TestClient, path: str, **params: Any):
    return client.get(path, params={k: v for k, v in params.items() if v is not None})


def _error(response) -> dict[str, Any]:
    return response.json()["detail"]


def _walk(client: TestClient, limit: int = 3, **filters: Any) -> list[str]:
    """Follow next_cursor to the end and return every run id in order."""
    ids: list[str] = []
    cursor = None
    for _ in range(500):
        response = _get(client, "/runs", limit=limit, cursor=cursor, **filters)
        assert response.status_code == 200, response.text
        page = response.json()
        ids += [item["run_id"] for item in page["items"]]
        cursor = page["next_cursor"]
        if cursor is None:
            return ids
    raise AssertionError("pagination did not terminate")


def _with_bundle(result: AnalysisResult, **bundle_changes) -> AnalysisResult:
    return result.model_copy(update={"bundle": result.bundle.model_copy(update=bundle_changes)})


def _change_item(result: AnalysisResult, evidence_id: str, **changes) -> AnalysisResult:
    items = tuple(
        i.model_copy(update=changes) if i.id == evidence_id else i for i in result.bundle.items
    )
    return _with_bundle(result, items=items)


# --- listing --------------------------------------------------------------------


class TestListRuns:
    def test_an_empty_store_lists_nothing(self, client):
        page = client.get("/runs").json()
        assert page == {"items": [], "next_cursor": None, "limit": 25, "contains_simulated": False}

    def test_newest_first(self, client, store, clock, completed):
        ids = [_save(store, clock, completed) for _ in range(4)]
        assert [i["run_id"] for i in client.get("/runs").json()["items"]] == ids[::-1]

    def test_a_run_lists_with_what_a_table_needs(self, client, store, clock, completed):
        run_id = _save(store, clock, completed)
        (item,) = client.get("/runs").json()["items"]
        assert item["run_id"] == run_id
        assert item["status"] == "succeeded" and item["result_state"] == "measured"
        assert item["verdict_label"] == completed.verdict_label
        assert item["engine_version"] == ENGINE_VERSION
        assert item["created_at"] == iso(clock.now)

    def test_a_walk_visits_every_run_once_in_order(self, client, store, clock, completed):
        ids = [_save(store, clock, completed) for _ in range(10)]
        assert _walk(client, limit=3) == ids[::-1]

    def test_the_page_sizes_are_as_asked(self, client, store, clock, completed):
        for _ in range(7):
            _save(store, clock, completed)
        first = client.get("/runs", params={"limit": 3}).json()
        assert len(first["items"]) == 3 and first["limit"] == 3 and first["next_cursor"]
        pages = []
        cursor = None
        while True:
            page = client.get(
                "/runs", params={"limit": 3, "cursor": cursor} if cursor else {"limit": 3}
            ).json()
            pages.append(len(page["items"]))
            cursor = page["next_cursor"]
            if cursor is None:
                break
        assert pages == [3, 3, 1]

    def test_an_exact_multiple_does_not_end_with_an_empty_page(
        self, client, store, clock, completed
    ):
        for _ in range(6):
            _save(store, clock, completed)
        second = client.get("/runs", params={"limit": 3}).json()
        last = client.get("/runs", params={"limit": 3, "cursor": second["next_cursor"]}).json()
        assert len(last["items"]) == 3 and last["next_cursor"] is None

    def test_runs_recorded_at_the_same_instant_are_still_paged_exactly_once(
        self, client, store, clock, completed
    ):
        ids = [f"run_{n:016x}" for n in range(9)]
        for run_id in ids:  # one clock instant for all of them
            store.save_result(completed.model_copy(update={"run_id": run_id}))
        assert _walk(client, limit=2) == sorted(ids, reverse=True)

    @pytest.mark.parametrize("limit", [0, -1, 101, 1000])
    def test_page_size_is_bounded(self, client, limit):
        assert client.get("/runs", params={"limit": limit}).status_code == 422

    def test_the_largest_page_is_allowed(self, client, store, clock, completed):
        _save(store, clock, completed)
        assert client.get("/runs", params={"limit": 100}).status_code == 200


class TestFilters:
    def test_by_case(self, client, store, clock, completed):
        mine = _save(store, clock, completed)
        _save(store, clock, completed, case_id="southern-cardamom-redd")
        assert [
            i["run_id"] for i in _get(client, "/runs", case_id="kariba-redd").json()["items"]
        ] == [mine]
        assert _get(client, "/runs", case_id="nope").json()["items"] == []

    def test_by_engine_version(self, client, store, clock, completed):
        current = _save(store, clock, completed)
        older = _save(
            store, clock, completed,
            engine=EngineRef(engine_version="0.9.0", contract_version=CONTRACT_VERSION),
        )  # fmt: skip

        def by(version):
            response = _get(client, "/runs", engine_version=version)
            return [i["run_id"] for i in response.json()["items"]]

        assert by(ENGINE_VERSION) == [current] and by("0.9.0") == [older] and by("1.0.0") == []

    def test_by_data_mode(self, client, store, clock, completed):
        simulated = _save(store, clock, completed)
        observed = _save(store, clock, completed, data_mode="observed", datasets=())

        def by(mode):
            response = _get(client, "/runs", data_mode=mode)
            return [i["run_id"] for i in response.json()["items"]]

        assert by("simulated") == [simulated] and by("observed") == [observed]
        assert client.get("/runs", params={"data_mode": "real"}).status_code == 422

    def test_by_status_one_or_several(self, client, store, clock, queue, completed, refused):
        done = _save(store, clock, completed)
        refusal = _save(store, clock, refused)
        failed = _save(
            store, clock, completed, status=EngineStatus.ERROR, bundle=None,
            error=AnalysisError(code=ErrorCode.ESTIMATION_FAILED, message="did not converge"),
        )  # fmt: skip
        clock.tick()
        waiting = queue.submit(_request(seed=11)).run_id
        clock.tick()
        cancelled = queue.submit(_request(seed=12)).run_id
        queue.cancel(cancelled)

        def ids(*statuses):
            response = client.get("/runs", params={"status": list(statuses)})
            return {i["run_id"] for i in response.json()["items"]}

        assert ids("queued") == {waiting}
        assert ids("cancelled") == {cancelled}
        assert ids("failed") == {failed}
        assert ids("succeeded") == {done, refusal}  # a refusal is a succeeded job
        assert ids("succeeded", "failed") == {done, refusal, failed}
        assert ids("queued", "queued") == {waiting}
        assert client.get("/runs", params={"status": "finished"}).status_code == 422

    def test_by_date_inclusive_after_exclusive_before(self, client, store, clock, completed):
        ids = [_save(store, clock, completed) for _ in range(5)]  # T0+1s .. T0+5s
        at = lambda s: iso(T0 + timedelta(seconds=s))  # noqa: E731

        def found(**kw):
            return [i["run_id"] for i in _get(client, "/runs", **kw).json()["items"]]

        assert found(created_after=at(2)) == ids[1:][::-1]  # the 2s run is included
        assert found(created_before=at(4)) == ids[:3][::-1]  # the 4s run is not
        assert found(created_after=at(2), created_before=at(4)) == [ids[2], ids[1]]
        assert found(created_after=at(10)) == []

    def test_a_date_with_another_offset_means_the_same_instant(
        self, client, store, clock, completed
    ):
        """12:00:03Z is 17:30:03 in +05:30; the filter must not read it as 17:30 UTC."""
        ids = [_save(store, clock, completed) for _ in range(5)]  # 12:00:01Z .. 12:00:05Z
        response = client.get("/runs", params={"created_after": "2026-11-01T17:30:03+05:30"})
        assert [i["run_id"] for i in response.json()["items"]] == ids[2:][::-1]

    def test_filters_combine(self, client, store, clock, completed):
        _save(store, clock, completed, case_id="southern-cardamom-redd")
        keep = _save(store, clock, completed)
        _save(store, clock, completed, data_mode="observed", datasets=())
        response = _get(
            client, "/runs", case_id="kariba-redd", data_mode="simulated", status="succeeded"
        )
        assert [i["run_id"] for i in response.json()["items"]] == [keep]

    def test_a_filtered_walk_pages_correctly(self, client, store, clock, completed):
        mine = [_save(store, clock, completed) for _ in range(5)]
        for _ in range(3):
            _save(store, clock, completed, case_id="southern-cardamom-redd")
        assert _walk(client, limit=2, case_id="kariba-redd") == mine[::-1]

    def test_a_date_without_a_timezone_is_refused(self, client):
        response = client.get("/runs", params={"created_after": "2026-11-01T00:00:00"})
        assert response.status_code == 422
        assert _error(response)["code"] == "invalid_filter"
        assert "Z" in _error(response)["hint"]

    def test_an_unparseable_date_is_refused(self, client):
        assert client.get("/runs", params={"created_after": "yesterday"}).status_code == 422

    def test_an_empty_date_range_is_refused(self, client):
        response = client.get("/runs", params={"created_after": iso(T0), "created_before": iso(T0)})
        assert response.status_code == 422 and _error(response)["code"] == "invalid_filter"


# --- cursors --------------------------------------------------------------------


def _token(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


class TestCursors:
    def _first_cursor(self, client, store, clock, completed, **params) -> str:
        for _ in range(4):
            _save(store, clock, completed)
        return _get(client, "/runs", limit=2, **params).json()["next_cursor"]

    def test_a_cursor_is_an_opaque_url_safe_token(self, client, store, clock, completed):
        cursor = self._first_cursor(client, store, clock, completed)
        assert cursor and all(c.isalnum() or c in "-_" for c in cursor)

    @pytest.mark.parametrize("bad", ["!!!not-a-cursor!!!", "", "e30", "AAAA"])
    def test_garbage_is_a_400(self, client, bad):
        response = client.get("/runs", params={"cursor": bad})
        assert response.status_code == 400
        assert _error(response)["code"] == "invalid_cursor"

    def test_the_wrong_shape_or_version_is_a_400(self, client):
        for payload in ({"v": 1}, {"v": 2, "t": "x", "r": "y", "f": "z"}, [1, 2]):
            response = client.get("/runs", params={"cursor": _token(payload)})  # type: ignore[arg-type]
            assert response.status_code == 400, payload

    def test_a_timestamp_without_a_timezone_is_a_400(self, client):
        token = _token(
            {
                "v": 1,
                "t": "2026-11-01T12:00:00",
                "r": "run_x",
                "f": filters_fingerprint(RunFilter()),
            }
        )
        assert client.get("/runs", params={"cursor": token}).status_code == 400

    def test_a_cursor_from_other_filters_is_refused(self, client, store, clock, completed):
        cursor = self._first_cursor(client, store, clock, completed)
        response = client.get("/runs", params={"cursor": cursor, "case_id": "kariba-redd"})
        assert response.status_code == 400
        assert "different filters" in _error(response)["message"]

    def test_the_same_filters_accept_the_cursor_whatever_the_page_size(
        self, client, store, clock, completed
    ):
        cursor = self._first_cursor(client, store, clock, completed, case_id="kariba-redd")
        response = client.get(
            "/runs", params={"cursor": cursor, "case_id": "kariba-redd", "limit": 50}
        )
        assert response.status_code == 200 and len(response.json()["items"]) == 2

    def test_the_order_of_repeated_statuses_does_not_matter(self, client, store, clock, completed):
        for _ in range(4):
            _save(store, clock, completed)
        cursor = client.get("/runs", params={"limit": 2, "status": ["succeeded", "failed"]}).json()[
            "next_cursor"
        ]
        response = client.get("/runs", params={"cursor": cursor, "status": ["failed", "succeeded"]})
        assert response.status_code == 200


# --- paging while runs are written ----------------------------------------------


class TestPaginationIsStable:
    def test_runs_written_between_pages_never_shift_or_repeat_a_page(
        self, client, store, clock, completed
    ):
        ids = [_save(store, clock, completed) for _ in range(12)]  # oldest .. newest
        first = client.get("/runs", params={"limit": 5}).json()
        assert [i["run_id"] for i in first["items"]] == ids[:6:-1]  # newest five

        for _ in range(6):  # six newer runs arrive while the reader is mid-scroll
            _save(store, clock, completed)

        second = client.get("/runs", params={"limit": 5, "cursor": first["next_cursor"]}).json()
        assert [i["run_id"] for i in second["items"]] == ids[6:1:-1]
        third = client.get("/runs", params={"limit": 5, "cursor": second["next_cursor"]}).json()
        assert [i["run_id"] for i in third["items"]] == ids[1::-1]
        assert third["next_cursor"] is None

    def test_a_run_changing_status_mid_scroll_neither_moves_nor_repeats(
        self, client, store, clock, sessions, completed
    ):
        """The sort key is fixed at creation; a job moving queued -> running -> done is not."""
        ids = [_save(store, clock, completed) for _ in range(8)]
        first = client.get("/runs", params={"limit": 3}).json()
        with sessions.begin() as session:
            session.get(AnalysisRunRow, ids[2]).status = "cancelled"
            session.get(AnalysisRunRow, ids[0]).status = "failed"
        rest = [first["items"]]
        cursor = first["next_cursor"]
        while cursor:
            page = client.get("/runs", params={"limit": 3, "cursor": cursor}).json()
            rest.append(page["items"])
            cursor = page["next_cursor"]
        assert [i["run_id"] for page in rest for i in page] == ids[::-1]

    def test_paging_while_another_thread_writes(self, sessions, clock, completed, monkeypatch):
        """Invariants that hold however the two interleave; nothing depends on timing."""
        configure_auth(monkeypatch)
        store = SqlEvidenceStore(sessions, clock=clock)
        store.upsert_case(get_case("kariba-redd"))
        originals = [_save(store, clock, completed) for _ in range(40)]
        app.dependency_overrides[get_store] = lambda: store
        written: list[str] = []
        errors: list[BaseException] = []
        start = threading.Barrier(2, timeout=30)

        def write() -> None:
            try:
                writer = SqlEvidenceStore(sessions, clock=clock)
                start.wait()
                for _ in range(60):
                    written.append(_save(writer, clock, completed))
            except BaseException as exc:
                errors.append(exc)

        thread = threading.Thread(target=write, daemon=True)
        thread.start()
        try:
            with TestClient(app, base_url=ORIGIN) as root:
                client = build_world(root, sessions, wire_jobs=False, backfill=True).client("ref")
                start.wait()
                seen = _walk(client, limit=7)
        finally:
            thread.join(timeout=60)
            app.dependency_overrides.clear()

        assert not thread.is_alive(), "the writer did not finish"
        assert not errors, errors
        assert len(seen) == len(set(seen)), "a run was returned twice"
        assert [r for r in seen if r in set(originals)] == originals[::-1], (
            "a run that existed before paging started was skipped, repeated or reordered"
        )
        with sessions() as session:
            created = dict(
                session.execute(sa.select(AnalysisRunRow.run_id, AnalysisRunRow.created_at)).all()
            )
        keys = [(created[r], r) for r in seen]
        assert keys == sorted(keys, reverse=True), "the listing is not in descending key order"


# --- the indexes serve the queries ----------------------------------------------


def _plans(sessions, action) -> list[str]:
    """The SQLite plan of every SELECT on analysis_runs that ``action`` runs."""
    engine = sessions.kw["bind"]
    captured: list[tuple[str, Any]] = []

    def grab(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT") and "analysis_runs" in statement:
            captured.append((statement, parameters))

    sa.event.listen(engine, "before_cursor_execute", grab)
    try:
        action()
    finally:
        sa.event.remove(engine, "before_cursor_execute", grab)
    assert captured, "the action ran no query"
    plans = []
    with engine.connect() as conn:
        for statement, parameters in captured:
            rows = conn.exec_driver_sql("EXPLAIN QUERY PLAN " + statement, parameters).all()
            plans.append(" | ".join(str(r[-1]) for r in rows))
    return plans


class TestIndexesServeTheListing:
    @pytest.mark.parametrize(
        ("params", "index"),
        [
            ({"case_id": "kariba-redd"}, "ix_analysis_runs_case_id_created_at_run_id"),
            ({"status": "succeeded"}, "ix_analysis_runs_status_created_at_run_id"),
            (
                {"engine_version": ENGINE_VERSION},
                "ix_analysis_runs_engine_version_created_at_run_id",
            ),
            # Every API listing is scoped to the caller's projects (#47, revision 0008), so
            # with no narrower filter the project index serves it.
            ({}, "ix_analysis_runs_project_id_created_at_run_id"),
            ({"created_after": iso(T0)}, "ix_analysis_runs_project_id_created_at_run_id"),
        ],
        ids=["case", "status", "engine_version", "no-filter", "date"],
    )
    def test_a_first_page_and_a_later_page_are_index_scans_with_no_sort(
        self, client, store, sessions, clock, completed, params, index
    ):
        for _ in range(3):
            _save(store, clock, completed)
        cursor = _get(client, "/runs", limit=1, **params).json()["next_cursor"]
        for page_params in ({"limit": 1}, {"limit": 1, "cursor": cursor}):
            (plan,) = _plans(sessions, lambda p=page_params: _get(client, "/runs", **p, **params))
            assert index in plan, plan
            if "project_id" in index:
                # Several projects: one indexed range per project, then a sort of the caller's
                # own runs only. Never a walk through every other organization's runs.
                assert "SCAN analysis_runs" not in plan, plan
            else:
                assert "TEMP B-TREE" not in plan, f"the database has to sort: {plan}"


# --- one run --------------------------------------------------------------------


class TestGetRun:
    def test_a_completed_run_comes_back_whole(self, client, store, clock, completed):
        run_id = _save(store, clock, completed)
        body = client.get(f"/runs/{run_id}").json()
        assert (body["status"], body["result_state"], body["engine_status"]) == (
            "succeeded", "measured", "completed",
        )  # fmt: skip
        assert body["has_bundle"] is True and len(body["bundle"]["items"]) > 10
        assert body["verdict_label"] == completed.verdict_label
        assert body["verdict_rationale"] and body["caveats"]
        assert any("SIMULATED DATA" in w for w in body["warnings"])
        assert body["engine"]["engine_version"] == ENGINE_VERSION
        assert body["seed"] == completed.seed and body["started_at"] == completed.started_at
        assert body["metrics"]["n_donors_admitted"] > 0
        assert body["error"] is None and body["failure_reason"] is None

    def test_the_bundle_in_the_response_is_the_stored_bundle(self, client, store, clock, completed):
        run_id = _save(store, clock, completed)
        served = client.get(f"/runs/{run_id}").json()["bundle"]
        assert served == json.loads(completed.bundle.to_json())

    def test_the_bundle_can_be_left_out(self, client, store, clock, completed):
        run_id = _save(store, clock, completed)
        body = client.get(f"/runs/{run_id}", params={"include_bundle": "false"}).json()
        assert body["bundle"] is None and body["has_bundle"] is True
        assert body["verdict_label"] == completed.verdict_label and body["caveats"]

    def test_no_report_unless_asked(self, client, store, clock, completed):
        run_id = _save(store, clock, completed)
        body = client.get(f"/runs/{run_id}").json()
        assert body["report_markdown"] is None and body["report_generator"] is None

    def test_the_report_is_the_deterministic_rendering_of_the_stored_bundle(
        self, client, store, clock, completed
    ):
        run_id = _save(store, clock, completed)
        body = client.get(
            f"/runs/{run_id}", params={"include_report": "true", "include_bundle": "false"}
        ).json()
        assert body["report_generator"] == "deterministic"
        assert body["report_markdown"] == render_deterministic(completed.bundle)
        assert body["bundle"] is None  # the report does not need the bundle sent too

    def test_a_refusal_has_no_report_even_when_asked(self, client, store, clock, refused):
        run_id = _save(store, clock, refused)
        body = client.get(f"/runs/{run_id}", params={"include_report": "true"}).json()
        assert body["result_state"] == "refused"
        assert body["report_markdown"] is None and body["report_generator"] is None

    def test_a_refusal_is_a_200_with_its_reason_not_an_error(self, client, store, clock, refused):
        run_id = _save(store, clock, refused)
        response = client.get(f"/runs/{run_id}")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "succeeded"  # the job worked
        assert body["result_state"] == "refused" and body["engine_status"] == "refused"
        assert body["is_refusal"] is True and body["error_code"] == "donor_pool_inadequate"
        assert body["error"]["is_refusal"] is True
        assert body["error"]["stage"] == "matching" and body["error"]["remediation"]
        assert body["error"]["detail"]["min_donors_required"] == 500
        assert body["has_bundle"] is False and body["bundle"] is None
        assert body["failure_reason"] is None

    def test_an_engine_error_is_failed_and_not_a_refusal(self, client, store, clock, completed):
        run_id = _save(
            store, clock, completed, status=EngineStatus.ERROR, bundle=None,
            error=AnalysisError(code=ErrorCode.ESTIMATION_FAILED, message="did not converge"),
        )  # fmt: skip
        body = client.get(f"/runs/{run_id}").json()
        assert (body["status"], body["result_state"]) == ("failed", "failed")
        assert body["is_refusal"] is False and body["error"]["is_refusal"] is False
        assert body["error"]["message"] == "did not converge"

    def test_a_queued_run_has_a_state_and_no_result(self, client, queue):
        run_id = queue.submit(_request()).run_id
        response = client.get(f"/runs/{run_id}")
        body = response.json()
        assert response.status_code == 200
        assert (body["status"], body["result_state"]) == ("queued", "queued")
        assert body["has_bundle"] is False and body["bundle"] is None and body["engine"] is None
        assert body["engine_status"] is None and body["verdict_label"] is None
        assert body["is_simulated"] is True  # known from the request, before anything ran

    def test_a_running_run(self, client, queue):
        run_id = queue.submit(_request()).run_id
        queue.claim("w1")
        assert client.get(f"/runs/{run_id}").json()["result_state"] == "running"

    def test_a_cancelled_run(self, client, queue):
        run_id = queue.submit(_request()).run_id
        queue.cancel(run_id)
        body = client.get(f"/runs/{run_id}").json()
        assert (body["status"], body["result_state"]) == ("cancelled", "cancelled")

    def test_a_run_that_failed_before_the_engine_says_why(self, client, queue, sessions):
        run_id = queue.submit(_request()).run_id
        with sessions.begin() as session:
            session.get(AnalysisRunRow, run_id).request = None  # unusable stored request
        assert queue.claim("w1") is None
        body = client.get(f"/runs/{run_id}").json()
        assert (body["status"], body["result_state"]) == ("failed", "failed")
        assert body["failure_reason"] == "unusable-request" and body["error"] is None

    def test_a_failure_reason_is_cut_short(self, client, queue, sessions):
        run_id = queue.submit(_request()).run_id
        with sessions.begin() as session:
            session.get(AnalysisRunRow, run_id).request = None
        queue.claim("w1")
        with sessions.begin() as session:
            session.get(JobRow, run_id).last_error = {"reason": "x" * 5000}
        assert len(client.get(f"/runs/{run_id}").json()["failure_reason"]) == 300

    def test_a_stored_engine_error_is_not_explained_twice(self, client, queue, completed):
        run_id = queue.submit(_request()).run_id
        job = queue.claim("w1")
        bad = completed.model_copy(update={
            "status": EngineStatus.ERROR, "bundle": None,
            "error": AnalysisError(code=ErrorCode.ESTIMATION_FAILED, message="no fit"),
        })  # fmt: skip
        queue.complete(job, bad)
        body = client.get(f"/runs/{run_id}").json()
        assert body["error"]["code"] == "estimation_failed" and body["failure_reason"] is None

    def test_an_unknown_run_is_a_404_with_a_code(self, client):
        response = client.get("/runs/run_0000000000000000")
        assert response.status_code == 404
        assert _error(response)["code"] == "run_not_found"

    def test_a_run_from_an_unreadable_contract_is_a_409(self, client, store, clock, completed):
        run_id = _save(store, clock, completed, contract_version="1.3.0")
        response = client.get(f"/runs/{run_id}")
        assert response.status_code == 409
        assert _error(response)["code"] == "contract_version_mismatch"

    def test_compare_is_not_taken_for_a_run_id(self, client):
        """GET /runs/compare with no arguments is a missing-parameter error, not a 404."""
        assert client.get("/runs/compare").status_code == 422


# --- simulated data is always labelled ------------------------------------------


def _run_objects(node: Any) -> list[dict[str, Any]]:
    found = []
    if isinstance(node, dict):
        if "run_id" in node and "status" in node and "data_mode" in node:
            found.append(node)
        for value in node.values():
            found += _run_objects(value)
    elif isinstance(node, list):
        for value in node:
            found += _run_objects(value)
    return found


class TestSimulatedDataIsLabelled:
    def test_every_run_object_in_every_response_says_so(
        self, client, store, clock, queue, completed, refused
    ):
        a = _save(store, clock, completed)
        b = _save(store, clock, refused)
        c = _save(store, clock, completed, data_mode="observed", datasets=())
        queued = queue.submit(_request(seed=99)).run_id

        responses = [
            client.get("/runs").json(),
            client.get(f"/runs/{a}").json(),
            client.get(f"/runs/{b}").json(),
            client.get(f"/runs/{queued}").json(),
            client.get("/runs/compare", params={"baseline": a, "candidate": a}).json(),
            client.get("/runs/compare", params={"baseline": a, "candidate": c}).json(),
        ]
        seen = 0
        for response in responses:
            for run in _run_objects(response):
                seen += 1
                assert isinstance(run["is_simulated"], bool), run
                assert run["data_mode"] in ("simulated", "observed")
                assert run["is_simulated"] == (run["data_mode"] == "simulated")
                assert bool(run["notice"]) == run["is_simulated"]
                if run["is_simulated"]:
                    assert run["notice"].startswith("SIMULATED DATA")
        assert seen >= 10

    def test_pages_and_comparisons_say_whether_they_contain_simulated_runs(
        self, client, store, clock, completed
    ):
        simulated = _save(store, clock, completed)
        observed = _save(store, clock, completed, data_mode="observed", datasets=())
        both = client.get("/runs").json()
        only_observed = client.get("/runs", params={"data_mode": "observed"}).json()
        assert both["contains_simulated"] is True and only_observed["contains_simulated"] is False
        pair = client.get("/runs/compare", params={"baseline": simulated, "candidate": observed})
        assert pair.json()["contains_simulated"] is True

    def test_an_observed_run_is_not_labelled_simulated(self, client, store, clock, completed):
        run_id = _save(store, clock, completed, data_mode="observed", datasets=())
        body = client.get(f"/runs/{run_id}").json()
        assert body["is_simulated"] is False and body["notice"] is None


# --- comparing ------------------------------------------------------------------


def _compare(client, baseline: str, candidate: str, **params):
    return client.get(
        "/runs/compare", params={"baseline": baseline, "candidate": candidate, **params}
    )


class TestCompare:
    def test_identical_runs_are_entirely_unchanged(self, client, store, clock, completed):
        a, b = _save(store, clock, completed), _save(store, clock, completed)
        body = _compare(client, a, b).json()
        assert body["comparable"] is True and body["not_comparable"] == []
        assert body["same_specification"] is True
        summary = body["diff"]["summary"]
        assert summary["unchanged"] == len(completed.bundle) and summary["changed"] == 0
        assert body["diff"]["items"] == []  # unchanged ids are counted, not listed
        assert body["diff"]["verdict"]["label_changed"] is False

    def test_unchanged_ids_are_listed_on_request(self, client, store, clock, completed):
        a, b = _save(store, clock, completed), _save(store, clock, completed)
        body = _compare(client, a, b, include_unchanged="true").json()
        assert [i["id"] for i in body["diff"]["items"]] == sorted(i.id for i in completed.bundle)

    def test_a_run_compared_with_itself_is_unchanged(self, client, store, clock, completed):
        a = _save(store, clock, completed)
        body = _compare(client, a, a).json()
        assert body["comparable"] and body["diff"]["summary"]["changed"] == 0

    def test_the_diff_is_per_evidence_id(self, client, store, clock, completed):
        base = _save(store, clock, completed)
        point = completed.bundle.require("effect.point_estimate")
        changed = _change_item(completed, "effect.point_estimate", value=point.value * 2)
        extra = point.model_copy(update={"id": "effect.extra_metric", "label": "Extra"})
        removed_id = "placebo.p_value"
        items = (*(i for i in changed.bundle.items if i.id != removed_id), extra)
        candidate = _save(store, clock, _with_bundle(changed, items=items))

        diff = _compare(client, base, candidate).json()["diff"]
        by_id = {i["id"]: i for i in diff["items"]}

        assert by_id["effect.point_estimate"]["status"] == "changed"
        assert by_id["effect.point_estimate"]["changes"][0]["field"] == "value"
        assert by_id["effect.point_estimate"]["delta"] == pytest.approx(point.value)
        assert by_id["effect.point_estimate"]["relative_delta"] == pytest.approx(1.0)
        assert by_id[removed_id]["status"] == "removed" and by_id[removed_id]["candidate"] is None
        assert by_id["effect.extra_metric"]["status"] == "added"
        assert by_id["effect.extra_metric"]["baseline"] is None
        assert diff["summary"] == {
            "added": 1, "removed": 1, "changed": 1, "unchanged": len(completed.bundle) - 2,
        }  # fmt: skip
        snapshot = by_id["effect.point_estimate"]["candidate"]
        assert snapshot["unit"] == point.unit and snapshot["provenance_fingerprint"]

    def test_a_changed_verdict_is_reported_neutrally(self, client, store, clock, completed):
        a = _save(store, clock, completed)
        verdict = completed.bundle.verdict.model_copy(
            update={"label": VerdictLabel.DIVERGENT_FROM_CLAIM, "divergence_ratio": 0.4}
        )
        b = _save(store, clock, _with_bundle(completed, verdict=verdict))
        v = _compare(client, a, b).json()["diff"]["verdict"]
        assert v["label_changed"] is True and v["divergence_ratio_changed"] is True
        assert v["baseline_label"] == completed.verdict_label
        assert v["candidate_label"] == "divergent_from_claim"

    def test_warnings_that_appear_or_disappear(self, client, store, clock, completed):
        a = _save(store, clock, completed)
        b = _save(
            store, clock, _with_bundle(completed, warnings=(*completed.bundle.warnings, "new"))
        )
        assert _compare(client, a, b).json()["diff"]["warnings"] == {
            "added": ["new"],
            "removed": [],
        }

    def test_a_different_specification_is_comparable_but_flagged(
        self, client, store, clock, completed
    ):
        a = _save(store, clock, completed)
        b = _save(store, clock, completed, spec_hash="f" * 32)
        body = _compare(client, a, b).json()
        assert body["comparable"] is True and body["same_specification"] is False
        assert body["diff"] is not None

    # --- NOT COMPARABLE -----------------------------------------------------------

    def test_across_engine_versions_is_not_comparable_and_shows_no_diff(
        self, client, store, clock, completed
    ):
        old = EngineRef(engine_version="0.9.0", contract_version=CONTRACT_VERSION)
        a = _save(store, clock, completed, engine=old)
        # a result that really would differ: the point estimate moved
        moved = _change_item(completed, "effect.point_estimate", value=123.0)
        b = _save(store, clock, moved)

        response = _compare(client, a, b)
        body = response.json()

        assert response.status_code == 200
        assert body["comparable"] is False
        assert body["diff"] is None  # no diff, not even a partial one
        (reason,) = body["not_comparable"]
        assert (reason["code"], reason["side"]) == ("different_engine_version", "both")
        assert "0.9.0" in reason["message"] and ENGINE_VERSION in reason["message"]
        assert body["baseline"]["engine_version"] == "0.9.0"  # both runs are still shown
        assert body["candidate"]["engine_version"] == ENGINE_VERSION

    def test_simulated_against_observed(self, client, store, clock, completed):
        a = _save(store, clock, completed)
        b = _save(store, clock, completed, data_mode="observed", datasets=())
        body = _compare(client, a, b).json()
        assert [r["code"] for r in body["not_comparable"]] == ["different_data_mode"]
        assert body["diff"] is None

    def test_different_cases(self, client, store, clock, completed):
        a = _save(store, clock, completed)
        b = _save(store, clock, completed, case_id="southern-cardamom-redd")
        body = _compare(client, a, b).json()
        assert [r["code"] for r in body["not_comparable"]] == ["different_case"]
        assert body["diff"] is None

    def test_several_reasons_are_all_reported(self, client, store, clock, completed):
        a = _save(store, clock, completed)
        b = _save(
            store, clock, completed, case_id="southern-cardamom-redd", data_mode="observed",
            datasets=(), engine=EngineRef(engine_version="0.9.0", contract_version=CONTRACT_VERSION),
        )  # fmt: skip
        codes = {r["code"] for r in _compare(client, a, b).json()["not_comparable"]}
        assert codes == {"different_case", "different_data_mode", "different_engine_version"}

    def test_a_refused_run_has_nothing_to_compare(self, client, store, clock, completed, refused):
        a = _save(store, clock, completed)
        b = _save(store, clock, refused)
        body = _compare(client, a, b).json()
        (reason,) = body["not_comparable"]
        assert (reason["code"], reason["side"]) == ("no_bundle", "candidate")
        assert "refused" in reason["message"] and "donor_pool_inadequate" in reason["message"]
        assert "legitimate" in reason["message"]
        assert body["diff"] is None
        assert body["candidate"]["result_state"] == "refused"

    def test_two_refusals(self, client, store, clock, refused):
        a, b = _save(store, clock, refused), _save(store, clock, refused)
        sides = [r["side"] for r in _compare(client, a, b).json()["not_comparable"]]
        assert sides == ["baseline", "candidate"]

    def test_unfinished_and_cancelled_runs(self, client, queue, clock):
        waiting = queue.submit(_request(seed=21)).run_id
        clock.tick()  # so "the oldest" is well defined, not decided by random run ids
        running = queue.submit(_request(seed=22)).run_id
        queue.claim("w1")  # takes the oldest: `waiting`
        cancelled = queue.submit(_request(seed=23)).run_id
        queue.cancel(cancelled)
        messages = {
            run_id: _compare(client, run_id, run_id).json()["not_comparable"][0]["message"]
            for run_id in (waiting, running, cancelled)
        }
        assert "still running" in messages[waiting]
        assert "still queued" in messages[running]
        assert "cancelled" in messages[cancelled]

    def test_an_unreadable_run_is_not_comparable_rather_than_an_error(
        self, client, store, clock, completed
    ):
        a = _save(store, clock, completed)
        b = _save(store, clock, completed, contract_version="1.3.0")
        response = _compare(client, a, b)
        assert response.status_code == 200
        codes = [(r["code"], r["side"]) for r in response.json()["not_comparable"]]
        assert codes == [("contract_unreadable", "candidate")]

    def test_a_different_contract_major_is_named(self, client, store, clock, completed):
        a = _save(store, clock, completed)
        b = _save(store, clock, completed, contract_version="2.0.0")
        codes = {r["code"] for r in _compare(client, a, b).json()["not_comparable"]}
        assert {"different_contract_major", "contract_unreadable"} <= codes

    def test_an_unknown_run_is_a_404_that_says_which(self, client, store, clock, completed):
        a = _save(store, clock, completed)
        missing = "run_ffffffffffffffff"
        first = _compare(client, missing, a)
        second = _compare(client, a, missing)
        assert first.status_code == second.status_code == 404
        assert "baseline" in _error(first)["message"] and "candidate" in _error(second)["message"]

    def test_both_run_ids_are_required(self, client, completed):
        assert client.get("/runs/compare", params={"baseline": "run_x"}).status_code == 422


# --- the store, directly --------------------------------------------------------


class TestStoreListing:
    def test_a_run_saved_without_a_job_lists_fine(self, store, clock, completed):
        run_id = _save(store, clock, completed)  # no jobs row at all
        (item,) = store.list_runs(RunFilter()).items
        assert item.run_id == run_id and item.failure_reason is None

    def test_limit_must_be_positive(self, store):
        with pytest.raises(ValueError):
            store.list_runs(RunFilter(), limit=0)

    def test_summary_for_tells_unknown_from_unfinished(self, store, queue, completed, clock):
        queued = queue.submit(_request()).run_id
        assert store.summary_for(queued).result_state == "queued"
        assert store.by_run_id(queued) is None
        assert store.summary_for("run_0000000000000000") is None

    def test_list_for_case_shows_a_failure_reason_too(self, store, queue, sessions):
        run_id = queue.submit(_request()).run_id
        with sessions.begin() as session:
            session.get(AnalysisRunRow, run_id).request = None
        queue.claim("w1")
        (summary,) = store.list_for_case("kariba-redd")
        assert summary.failure_reason == "unusable-request"


# --- when there is no store -----------------------------------------------------


class TestStoreUnavailable:
    """The old endpoints must keep working however the store is (not) set up."""

    def _plain_client(self) -> TestClient:
        app.dependency_overrides.clear()
        return TestClient(app)

    def _assert_old_endpoints_work(self, client: TestClient) -> None:
        """``/health`` needs nothing. The case routes are project-scoped now: with no session
        they answer 401 on their own, without touching the (missing or broken) store."""
        assert client.get("/health").status_code == 200
        assert client.get("/cases").status_code == 401
        assert client.get("/cases/kariba-redd").status_code == 401

    def _sign_in(self, client: TestClient, monkeypatch) -> None:
        """Register and give the user an organization, on the database the app now builds."""
        configure_auth(monkeypatch)
        client.headers["Origin"] = ORIGIN
        assert register(client, "a@example.org").status_code in (200, 201)
        assert client.post("/orgs", json={"name": "Org", "type": "ngo"}).status_code == 201

    def test_no_database_url(self, monkeypatch):
        monkeypatch.setattr(database, "get_settings", lambda: SimpleNamespace(database_url=None))
        client = self._plain_client()
        for path in ("/runs", "/runs/run_0000000000000000", "/runs/compare?baseline=a&candidate=b"):
            response = client.get(path)
            assert response.status_code == 503, path
            assert _error(response)["code"] == "store_not_configured"
            assert "DATABASE_URL" in _error(response)["hint"]
        self._assert_old_endpoints_work(client)

    def test_a_database_behind_the_migrations(self, monkeypatch, url):
        monkeypatch.setattr(database, "get_settings", lambda: SimpleNamespace(database_url=url))
        client = self._plain_client()
        response = client.get("/runs")
        assert response.status_code == 503
        assert _error(response)["code"] == "store_not_configured"
        assert "--migrate" in _error(response)["hint"]
        self._assert_old_endpoints_work(client)

    def test_a_database_that_cannot_be_reached(self, monkeypatch, url):
        monkeypatch.setattr(database, "get_settings", lambda: SimpleNamespace(database_url=url))

        def unreachable(_url=None):
            raise sa.exc.OperationalError("SELECT", {}, Exception("connection refused"))

        monkeypatch.setattr(migrate, "is_at_head", unreachable)
        client = self._plain_client()
        response = client.get("/runs")
        assert response.status_code == 503 and _error(response)["code"] == "store_unavailable"
        self._assert_old_endpoints_work(client)

    def test_the_db_extra_not_installed(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "sqlalchemy", None)  # `import sqlalchemy` now fails
        client = self._plain_client()
        response = client.get("/runs")
        assert response.status_code == 503 and _error(response)["code"] == "store_not_configured"
        assert "not installed" in _error(response)["message"]
        self._assert_old_endpoints_work(client)

    def test_a_configured_database_is_built_once_and_kept(self, monkeypatch, url, sessions):
        monkeypatch.setattr(database, "get_settings", lambda: SimpleNamespace(database_url=url))
        client = self._plain_client()
        self._sign_in(client, monkeypatch)
        assert client.get("/runs").json()["items"] == []
        first = dependencies.get_store()
        assert dependencies.get_store() is first

    def test_a_failed_attempt_is_not_remembered(self, monkeypatch, url):
        monkeypatch.setattr(database, "get_settings", lambda: SimpleNamespace(database_url=url))
        client = self._plain_client()
        assert client.get("/runs").status_code == 503  # not migrated yet
        migrate.upgrade(url)
        self._sign_in(client, monkeypatch)
        assert client.get("/runs").status_code == 200  # fixed, with no restart

    def test_a_database_that_stops_answering_mid_request(self, client, sessions):
        class Dying:
            _sessions = sessions  # sign-in still works; only the run listing fails

            def list_runs(self, *a, **k):
                raise sa.exc.OperationalError(
                    "SELECT", {}, Exception("server closed the connection")
                )

        app.dependency_overrides[get_store] = lambda: Dying()
        response = client.get("/runs")
        assert response.status_code == 503 and _error(response)["code"] == "store_unavailable"

    def test_inconsistent_stored_data_is_a_500_with_a_code(self, client, sessions):
        class Corrupt:
            _sessions = sessions

            def list_runs(self, *a, **k):
                raise StoreError("run 'x' completed but has no stored bundle")

        app.dependency_overrides[get_store] = lambda: Corrupt()
        response = client.get("/runs")
        assert response.status_code == 500 and _error(response)["code"] == "store_error"


# --- errors, schema, and the migration ------------------------------------------


class TestErrorsAndSchema:
    def test_every_api_error_code_has_a_status(self):
        assert set(ApiErrorCode) == set(API_ERROR_STATUS)

    def test_the_shared_code_keeps_the_status_the_engine_path_uses(self):
        assert (
            API_ERROR_STATUS[ApiErrorCode.CONTRACT_VERSION_MISMATCH]
            == ERROR_STATUS[ErrorCode.CONTRACT_VERSION_MISMATCH]
        )
        assert (
            ApiErrorCode.CONTRACT_VERSION_MISMATCH.value
            == ErrorCode.CONTRACT_VERSION_MISMATCH.value
        )

    def test_the_openapi_schema_describes_the_new_endpoints(self):
        schema = TestClient(app).get("/openapi.json").json()
        assert {"/runs", "/runs/compare", "/runs/{run_id}"} <= set(schema["paths"])
        assert {"/health", "/cases", "/cases/{case_id}", "/cases/{case_id}/verify"} <= set(
            schema["paths"]
        )  # the frontend's endpoints are still there
        for name in ("RunListPage", "RunDetail", "RunComparison", "RunItem", "NotComparable",
                     "BundleDiff", "ItemDiff", "ApiErrorBody"):  # fmt: skip
            assert name in schema["components"]["schemas"], name
        assert "cursor" in {p["name"] for p in schema["paths"]["/runs"]["get"]["parameters"]}

    def test_the_existing_verify_response_is_unchanged(self):
        schema = TestClient(app).get("/openapi.json").json()["components"]["schemas"]
        assert set(schema["VerificationResponse"]["properties"]) == {
            "run_id", "case_id", "spec_hash", "engine_version", "contract_version", "duration_ms",
            "data_mode", "verdict_label", "verdict_rationale", "caveats", "warnings", "bundle",
            "report_markdown", "report_generator",
        }  # fmt: skip


class TestMigration0004:
    @staticmethod
    def _indexes(url: str) -> dict[str, set[tuple[str, tuple[str, ...], bool]]]:
        inspector = sa.inspect(create_db_engine(url))
        return {
            table: {
                (i["name"], tuple(i["column_names"]), bool(i["unique"]))
                for i in inspector.get_indexes(table)
            }
            for table in sorted(inspector.get_table_names())
            if table != "alembic_version"
        }

    def test_downgrade_restores_the_original_indexes_exactly(self, tmp_path):
        before = f"sqlite:///{tmp_path / 'before.db'}"
        migrate.upgrade(before, "0003")
        original = self._indexes(before)

        after = f"sqlite:///{tmp_path / 'after.db'}"
        migrate.upgrade(after)
        assert self._indexes(after) != original  # the upgrade really changed them
        migrate.downgrade(after, "0003")

        assert self._indexes(after) == original

    def test_the_upgrade_adds_exactly_the_new_indexes(self, tmp_path):
        old, new = f"sqlite:///{tmp_path / 'old.db'}", f"sqlite:///{tmp_path / 'new.db'}"
        migrate.upgrade(old, "0003")
        migrate.upgrade(new, "0004")  # 0004 itself, not whatever later revisions add
        before, after = self._indexes(old)["analysis_runs"], self._indexes(new)["analysis_runs"]
        assert {i[0] for i in before - after} == {
            "ix_analysis_runs_case_id_created_at",
            "ix_analysis_runs_status_created_at",
            "ix_analysis_runs_created_at",
        }
        assert {(i[0], i[1]) for i in after - before} == {
            ("ix_analysis_runs_case_id_created_at_run_id", ("case_id", "created_at", "run_id")),
            ("ix_analysis_runs_status_created_at_run_id", ("status", "created_at", "run_id")),
            ("ix_analysis_runs_engine_version_created_at_run_id",
             ("engine_version", "created_at", "run_id")),
            ("ix_analysis_runs_created_at_run_id", ("created_at", "run_id")),
        }  # fmt: skip

    def test_the_cycle_can_be_repeated(self, tmp_path):
        url = f"sqlite:///{tmp_path / 'cycle.db'}"
        migrate.upgrade(url)
        migrate.downgrade(url)
        migrate.upgrade(url)
        assert migrate.is_at_head(url)
