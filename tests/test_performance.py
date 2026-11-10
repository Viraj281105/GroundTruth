"""Performance (#47): listing and claiming stay indexed as runs pile up, interactive work is not
starved by batch work, and a repeated spec is answered from the store.

"Does not degrade with run count" is checked with **query plans, not timings**: for every
listing filter, the worker's claim, its lease reaper and the cache lookup, SQLite must use an
index and never scan a whole table. CI has no PostgreSQL; the same indexes serve it (they are
created by the same migration), but its planner is not exercised here.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa

from groundtruth.platform.cases.registry import get_case
from groundtruth.platform.datasets.access import synthetic_access
from groundtruth.platform.datasets.synthetic import pinned_true_effect, simulation_pin
from groundtruth.platform.jobs import entrypoint
from groundtruth.platform.jobs.queue import JobQueue
from groundtruth.platform.jobs.worker import DEFAULT_TRUE_EFFECT, default_resolve_access
from groundtruth.platform.store import migrate
from groundtruth.platform.store.database import create_db_engine, create_session_factory
from groundtruth.platform.store.interface import RunCursor, RunFilter
from groundtruth.platform.store.models import AnalysisRunRow, JobRow
from groundtruth.platform.store.sql import SqlEvidenceStore

SEED = 20260101


class Captured:
    """A migrated SQLite database that records every statement it runs."""

    def __init__(self, tmp: Path) -> None:
        url = f"sqlite:///{tmp / 'perf.db'}"
        migrate.upgrade(url)
        self.engine = create_db_engine(url)
        self.sessions = create_session_factory(self.engine)
        self.statements: list[tuple[str, Any]] = []
        sa.event.listen(self.engine, "before_cursor_execute", self._record)

    def _record(self, conn: Any, cursor: Any, statement: str, params: Any, *rest: Any) -> None:
        if not statement.startswith("EXPLAIN"):
            self.statements.append((statement, params))

    def take(self) -> list[tuple[str, Any]]:
        taken, self.statements = self.statements, []
        return taken

    def plan(self, statement: str, params: Any) -> list[str]:
        with self.engine.connect() as connection:
            rows = connection.exec_driver_sql("EXPLAIN QUERY PLAN " + statement, params)
            return [str(row[-1]) for row in rows]


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Captured]:
    captured = Captured(tmp_path)
    yield captured
    captured.engine.dispose()


def _full_scans(plan: list[str]) -> list[str]:
    """Plan lines that read a whole runs or jobs table (a walk along an index is fine)."""
    return [
        line
        for line in plan
        if line.startswith("SCAN") and "INDEX" not in line and ("runs" in line or "jobs" in line)
    ]


def _request(*, effect: float = 0.06, min_donors: int | None = None) -> Any:
    return get_case("kariba-redd").to_request(
        data_mode="simulated", seed=SEED, min_donors=min_donors, datasets=(simulation_pin(effect),)
    )


# --- listing queries do not degrade with run count ---------------------------------------------

CURSOR = RunCursor(created_at=datetime(2030, 1, 1, tzinfo=UTC), run_id="run_ffffffffffffffff")
LISTINGS: dict[str, tuple[RunFilter, str]] = {
    "everything (an operator)": (RunFilter(), "ix_analysis_runs_created_at_run_id"),
    "one project (every UI listing)": (
        RunFilter(project_ids=("p1",)),
        "ix_analysis_runs_project_id_created_at_run_id",
    ),
    "several projects": (
        RunFilter(project_ids=("p1", "p2", "p3")),
        "ix_analysis_runs_project_id_created_at_run_id",
    ),
    "one case": (RunFilter(case_id="kariba-redd"), "ix_analysis_runs_case_id_created_at_run_id"),
    "a status": (RunFilter(statuses=("succeeded",)), "ix_analysis_runs_status_created_at_run_id"),
    "an engine version": (
        RunFilter(engine_version="1.0.0"),
        "ix_analysis_runs_engine_version_created_at_run_id",
    ),
}


class TestQueriesUseIndexes:
    @pytest.mark.parametrize("label", list(LISTINGS))
    @pytest.mark.parametrize("page", ["first", "later"])
    def test_every_listing_is_an_index_range(self, db, label, page):
        filters, index = LISTINGS[label]
        SqlEvidenceStore(db.sessions).list_runs(
            filters, limit=25, after=CURSOR if page == "later" else None
        )
        (statement,) = [s for s in db.take() if "FROM analysis_runs" in s[0]]
        plan = db.plan(*statement)
        assert any(index in line for line in plan), plan
        assert _full_scans(plan) == [], plan

    def test_the_worker_reaper_uses_the_lease_index(self, db):
        JobQueue(db.sessions).reap_expired()
        statements = [s for s in db.take() if "lease_expires_at <" in s[0]]
        assert statements
        for statement in statements:
            plan = db.plan(*statement)
            assert any("ix_jobs_lease_expires_at" in line for line in plan), plan
            assert _full_scans(plan) == [], plan

    @pytest.mark.parametrize("cap", [None, 1])
    def test_a_claim_looks_only_at_queued_jobs(self, db, cap):
        JobQueue(db.sessions, batch_max_running=cap)._claim_one("w1")
        (statement,) = [s for s in db.take() if s[0].startswith("UPDATE analysis_runs SET status")]
        plan = db.plan(*statement)
        assert any("ix_analysis_runs_status_created_at_run_id" in line for line in plan), plan
        assert _full_scans(plan) == [], plan

    def test_the_cache_and_duplicate_lookups_use_the_spec_hash(self, db):
        queue = JobQueue(db.sessions)
        SqlEvidenceStore(db.sessions).upsert_case(get_case("kariba-redd"))
        db.take()
        queue.submit(_request())
        lookups = [
            s for s in db.take() if s[0].lstrip().startswith("SELECT") and "spec_hash" in s[0]
        ]
        assert lookups
        for statement in lookups:
            plan = db.plan(*statement)
            assert _full_scans(plan) == [], plan
            assert any("INDEX" in line for line in plan), plan


# --- interactive work is not starved by batch work ---------------------------------------------


def _submit(db: Captured, queue: JobQueue, *, lane: str, min_donors: int) -> str:
    SqlEvidenceStore(db.sessions).upsert_case(get_case("kariba-redd"))
    return queue.submit(_request(min_donors=min_donors), lane=lane).run_id  # type: ignore[arg-type]


def _lane_of(db: Captured, run_id: str) -> str:
    with db.sessions() as session:
        return str(session.get(JobRow, run_id).lane)


class TestLanes:
    def test_submissions_are_batch_unless_a_person_is_waiting(self, db):
        queue = JobQueue(db.sessions)
        SqlEvidenceStore(db.sessions).upsert_case(get_case("kariba-redd"))
        default = queue.submit(_request(min_donors=31)).run_id  # the CLI and case creation
        assert _lane_of(db, default) == "batch"
        assert _lane_of(db, _submit(db, queue, lane="interactive", min_donors=32)) == "interactive"

    def test_an_interactive_job_is_claimed_before_older_batch_jobs(self, db):
        queue = JobQueue(db.sessions)
        batch = [_submit(db, queue, lane="batch", min_donors=31 + i) for i in range(3)]
        person = _submit(db, queue, lane="interactive", min_donors=40)
        order = [queue.claim("w").run_id for _ in range(4)]
        assert order == [person, *batch]  # oldest first within a lane

    def test_the_batch_cap_keeps_capacity_for_interactive_work(self, db):
        queue = JobQueue(db.sessions, batch_max_running=1)
        first, second = (_submit(db, queue, lane="batch", min_donors=31 + i) for i in range(2))
        assert queue.claim("w1").run_id == first  # one batch job running: the cap is reached
        assert queue.claim("w2") is None  # the second batch job waits
        person = _submit(db, queue, lane="interactive", min_donors=40)
        assert queue.claim("w2").run_id == person  # a person is never held back by the cap
        with db.sessions.begin() as session:  # the running batch job finishes
            session.get(AnalysisRunRow, first).status = "succeeded"
        assert queue.claim("w3").run_id == second

    def test_with_no_cap_batch_work_uses_every_worker(self, db):
        queue = JobQueue(db.sessions)
        jobs = [_submit(db, queue, lane="batch", min_donors=31 + i) for i in range(2)]
        assert [queue.claim(f"w{i}").run_id for i in range(2)] == jobs

    def test_the_worker_reads_the_cap_from_the_environment(self, monkeypatch):
        monkeypatch.setenv("WORKER_BATCH_MAX_RUNNING", "2")
        assert entrypoint.build_parser().parse_args([]).batch_max_running == 2
        monkeypatch.delenv("WORKER_BATCH_MAX_RUNNING")
        assert entrypoint.build_parser().parse_args([]).batch_max_running is None

    def test_post_jobs_submits_in_the_interactive_lane(self, tenant_world):
        response = tenant_world.client("ref").post(
            "/jobs", json={"case_id": "kariba-redd", "synthetic": True}
        )
        with tenant_world.sessions() as session:
            assert session.get(JobRow, response.json()["run_id"]).lane == "interactive"


# --- the simulation is part of the specification (the cache cannot mix effects) -----------------


class TestThePinnedSimulation:
    def test_post_jobs_pins_the_simulation_and_its_effect(self, tenant_world):
        from groundtruth.contracts.request import AnalysisRequest

        run_id = (
            tenant_world.client("ref")
            .post("/jobs", json={"case_id": "kariba-redd", "synthetic": True})
            .json()["run_id"]
        )
        with tenant_world.sessions() as session:
            stored = AnalysisRequest.model_validate(session.get(AnalysisRunRow, run_id).request)
        assert pinned_true_effect(stored) == DEFAULT_TRUE_EFFECT

    def test_the_verify_slider_is_pinned_the_same_way(self, tenant_world):
        client = tenant_world.client("ref")
        a = client.post("/cases/kariba-redd/verify", json={"true_effect": 0.06}).json()
        b = client.post("/cases/kariba-redd/verify", json={"true_effect": 0.02}).json()
        assert a["spec_hash"] == _request(effect=0.06).spec_hash
        assert b["spec_hash"] == _request(effect=0.02).spec_hash != a["spec_hash"]

    def test_a_different_effect_is_a_different_specification(self):
        assert _request(effect=0.06).spec_hash != _request(effect=0.0).spec_hash

    def test_the_worker_runs_the_pinned_effect_not_its_own_default(self):
        def injected(access: Any) -> float:
            return float(access.observations._provider.true_effect)

        resolve = default_resolve_access(true_effect=0.5)  # a worker started with another effect
        assert injected(resolve(_request(effect=0.0))) == 0.0  # the request's pin wins
        legacy = get_case("kariba-redd").to_request(seed=SEED)
        assert injected(resolve(legacy)) == 0.5  # an unpinned request gets the worker's default

    def test_a_run_cannot_compute_an_effect_its_request_does_not_specify(self):
        with pytest.raises(ValueError, match=r"pins true_effect=0.06"):
            synthetic_access(_request(effect=0.06), true_effect=0.5)

    def test_a_request_without_a_pin_still_runs_as_before(self):
        legacy = get_case("kariba-redd").to_request(seed=SEED)
        assert pinned_true_effect(legacy) is None
        assert synthetic_access(legacy, true_effect=0.06) is not None


def test_the_migration_adds_the_lane_and_the_indexes(tmp_path: Path):
    url = f"sqlite:///{tmp_path / 'm.db'}"
    migrate.upgrade(url)
    engine = create_db_engine(url)
    inspector = sa.inspect(engine)
    assert "lane" in {c["name"] for c in inspector.get_columns("jobs")}
    assert "ix_jobs_lease_expires_at" in {i["name"] for i in inspector.get_indexes("jobs")}
    runs = {i["name"] for i in inspector.get_indexes("analysis_runs")}
    assert "ix_analysis_runs_project_id_created_at_run_id" in runs
    engine.dispose()
