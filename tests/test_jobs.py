"""The analysis job lifecycle (issue #24).

Runs on SQLite through the real migrations. A fake clock drives every lease and backoff,
so no test sleeps. Engine results are real engine output on the synthetic fixture
(SIMULATED DATA), replayed by a stand-in engine where a test needs a specific outcome.
"""

from __future__ import annotations

import ast
import pathlib
import threading
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session, sessionmaker

from groundtruth.contracts.errors import DataUnavailableError
from groundtruth.contracts.identifiers import new_run_id
from groundtruth.contracts.request import AnalysisRequest
from groundtruth.contracts.result import (
    AnalysisError,
    AnalysisResult,
    AnalysisStatus,
    EngineStatus,
    ErrorCode,
)
from groundtruth.engine import run_analysis
from groundtruth.platform.cases.registry import get_case
from groundtruth.platform.datasets.access import synthetic_access
from groundtruth.platform.jobs.lifecycle import (
    DEFAULT_LEASE,
    TRANSITIONS,
    IllegalTransitionError,
    JobCancelledError,
    JobNotFoundError,
    LeaseLostError,
    backoff_delay,
    check_transition,
)
from groundtruth.platform.jobs.queue import JobQueue
from groundtruth.platform.jobs.runner import process_next
from groundtruth.platform.store import migrate
from groundtruth.platform.store.database import create_db_engine, create_session_factory
from groundtruth.platform.store.interface import UnknownCaseError
from groundtruth.platform.store.models import AnalysisRunRow, EvidenceBundleRow, JobRow
from groundtruth.platform.store.sql import SqlEvidenceStore

QUEUED, RUNNING, SUCCEEDED, FAILED, CANCELLED = (
    AnalysisStatus.QUEUED,
    AnalysisStatus.RUNNING,
    AnalysisStatus.SUCCEEDED,
    AnalysisStatus.FAILED,
    AnalysisStatus.CANCELLED,
)
T0 = datetime(2026, 11, 1, 12, 0, 0, tzinfo=UTC)
JOBS_DIR = (
    pathlib.Path(__file__).resolve().parents[1]
    / "packages"
    / "groundtruth"
    / "src"
    / "groundtruth"
    / "platform"
    / "jobs"
)


class FakeClock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now

    def tick(self, delta: timedelta = timedelta(seconds=1)) -> datetime:
        self.now += delta
        return self.now


class Engine:
    """A stand-in for ``run_analysis``: replays prepared results and counts calls.

    Like the real engine it mints a fresh ``run_id`` per call, so the tests see the
    job layer relabel it.
    """

    def __init__(self, *outcomes: AnalysisResult | Exception, on_call=None) -> None:
        self.outcomes = outcomes
        self.calls = 0
        self.on_call = on_call

    def __call__(self, request: AnalysisRequest, data) -> AnalysisResult:
        self.calls += 1
        if self.on_call is not None:
            self.on_call()
        outcome = self.outcomes[min(self.calls, len(self.outcomes)) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome.model_copy(update={"run_id": new_run_id()})


def _request(*, seed: int = 20260101, min_donors: int | None = None) -> AnalysisRequest:
    return get_case("kariba-redd").to_request(seed=seed, min_donors=min_donors)


def _access(request: AnalysisRequest):
    return synthetic_access(request, true_effect=0.06)


def _engine_error(result: AnalysisResult, code: ErrorCode) -> AnalysisResult:
    return result.model_copy(
        update={
            "status": EngineStatus.ERROR,
            "bundle": None,
            "error": AnalysisError(code=code, message=f"simulated {code.value}"),
        }
    )


@pytest.fixture(scope="module")
def completed() -> AnalysisResult:
    """A real completed engine run for ``_request()``, on SIMULATED DATA."""
    request = _request()
    result = run_analysis(request, _access(request))
    assert result.status is EngineStatus.COMPLETED and result.spec_hash == request.spec_hash
    return result


@pytest.fixture(scope="module")
def refused() -> AnalysisResult:
    """A real refusal: no pool of 500 donors exists."""
    request = _request(min_donors=500)
    result = run_analysis(request, _access(request))
    assert result.status is EngineStatus.REFUSED
    return result


@pytest.fixture
def url(tmp_path: pathlib.Path) -> str:
    return f"sqlite:///{tmp_path / 'jobs.db'}"


def _sessions(url: str) -> sessionmaker[Session]:
    # A generous busy timeout: concurrent SQLite writers wait for the lock, not fail.
    return create_session_factory(create_db_engine(url, connect_args={"timeout": 30}))


@pytest.fixture
def sessions(url: str) -> sessionmaker[Session]:
    migrate.upgrade(url)
    return _sessions(url)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def store(sessions: sessionmaker[Session], clock: FakeClock) -> SqlEvidenceStore:
    store = SqlEvidenceStore(sessions, clock=clock)
    store.upsert_case(get_case("kariba-redd"))
    return store


@pytest.fixture
def queue(sessions: sessionmaker[Session], clock: FakeClock, store) -> JobQueue:
    return JobQueue(sessions, clock=clock)


def _job(sessions: sessionmaker[Session], run_id: str) -> JobRow:
    with sessions() as session:
        row = session.get(JobRow, run_id)
        assert row is not None
        return row


def _count(sessions: sessionmaker[Session], model) -> int:
    with sessions() as session:
        return session.scalar(sa.select(sa.func.count()).select_from(model))


# --- the state machine ----------------------------------------------------------


class TestStateMachine:
    EXPECTED = {
        (QUEUED, RUNNING),
        (QUEUED, CANCELLED),
        (RUNNING, SUCCEEDED),
        (RUNNING, FAILED),
        (RUNNING, QUEUED),
        (RUNNING, CANCELLED),
    }

    @pytest.mark.parametrize("current", list(AnalysisStatus))
    @pytest.mark.parametrize("target", list(AnalysisStatus))
    def test_every_pair_is_allowed_or_refused_as_designed(self, current, target):
        if (current, target) in self.EXPECTED:
            check_transition(current, target)
        else:
            with pytest.raises(IllegalTransitionError):
                check_transition(current, target)

    def test_the_table_is_exactly_the_design(self):
        assert set(TRANSITIONS) == self.EXPECTED

    def test_terminal_statuses_have_no_way_out(self):
        for status in AnalysisStatus:
            if status.is_terminal:
                assert not [t for (c, t) in TRANSITIONS if c is status]

    def test_backoff_doubles_from_30s_and_is_capped(self):
        delays = [backoff_delay(n).total_seconds() for n in range(1, 8)]
        assert delays == [30, 60, 120, 240, 480, 900, 900]
        assert backoff_delay(10_000) == timedelta(minutes=15)
        with pytest.raises(ValueError):
            backoff_delay(0)


# --- the rule most likely to be got wrong ---------------------------------------


class TestARefusalIsASuccessfulJob:
    def test_a_real_refusal_is_succeeded_and_refused_never_failed(
        self, queue: JobQueue, store: SqlEvidenceStore
    ):
        submission = queue.submit(_request(min_donors=500))

        status = process_next(queue, "w1", _access)

        assert status is SUCCEEDED
        job = queue.status(submission.run_id)
        assert (job.status, job.engine_status) == (SUCCEEDED, "refused")
        stored = store.by_run_id(submission.run_id)
        assert stored.status is EngineStatus.REFUSED and stored.error.is_refusal
        assert stored.bundle is None
        (summary,) = store.list_for_case("kariba-redd")
        assert summary.status == "succeeded"

    def test_complete_maps_a_refusal_to_succeeded(self, queue: JobQueue, refused):
        queue.submit(_request(min_donors=500))
        job = queue.claim("w1")
        assert queue.complete(job, refused) is SUCCEEDED

    def test_a_real_completed_run_reloads_under_the_jobs_run_id(
        self, queue: JobQueue, store: SqlEvidenceStore
    ):
        submission = queue.submit(_request())
        produced: list[AnalysisResult] = []

        def engine(request, data):
            produced.append(run_analysis(request, data))
            return produced[-1]

        assert process_next(queue, "w1", _access, run=engine) is SUCCEEDED

        (original,) = produced
        assert original.run_id != submission.run_id  # the engine minted its own id
        assert store.by_run_id(submission.run_id) == original.model_copy(
            update={"run_id": submission.run_id}
        )
        assert store.by_run_id(original.run_id) is None  # nothing stored under the engine's id


# --- failures and retries -------------------------------------------------------


class TestRetry:
    def test_an_engine_error_that_cannot_pass_fails_at_once(
        self, queue: JobQueue, store: SqlEvidenceStore, completed
    ):
        submission = queue.submit(_request())
        engine = Engine(_engine_error(completed, ErrorCode.ESTIMATION_FAILED))

        assert process_next(queue, "w1", _access, run=engine) is FAILED

        assert engine.calls == 1
        assert queue.status(submission.run_id).attempts == 1
        stored = store.by_run_id(submission.run_id)
        assert stored.error.code is ErrorCode.ESTIMATION_FAILED

    def test_data_unavailable_is_retried_with_backoff_then_fails(
        self, queue: JobQueue, store: SqlEvidenceStore, clock: FakeClock, completed
    ):
        submission = queue.submit(_request())
        engine = Engine(_engine_error(completed, ErrorCode.DATA_UNAVAILABLE))

        assert process_next(queue, "w1", _access, run=engine) is QUEUED
        status = queue.status(submission.run_id)
        assert (status.attempts, status.available_at) == (1, T0 + timedelta(seconds=30))
        assert status.last_error["reason"] == "engine-error"
        assert store.by_run_id(submission.run_id) is None  # a retried attempt is not stored

        assert process_next(queue, "w1", _access, run=engine) is None  # still backing off

        clock.tick(timedelta(seconds=30))
        assert process_next(queue, "w1", _access, run=engine) is QUEUED
        assert queue.status(submission.run_id).available_at == clock.now + timedelta(seconds=60)

        clock.tick(timedelta(seconds=60))
        assert process_next(queue, "w1", _access, run=engine) is FAILED
        assert engine.calls == 3
        stored = store.by_run_id(submission.run_id)
        assert (stored.run_id, stored.error.code) == (submission.run_id, ErrorCode.DATA_UNAVAILABLE)

    def test_unavailable_data_access_is_retried(self, queue: JobQueue, completed):
        submission = queue.submit(_request())

        def no_data(request):
            raise DataUnavailableError("upstream outage")

        engine = Engine(completed)
        assert process_next(queue, "w1", no_data, run=engine) is QUEUED
        assert engine.calls == 0
        error = queue.status(submission.run_id).last_error
        assert error["retryable"] is True and "upstream outage" in error["reason"]

    def test_a_bug_fails_the_job_without_retry_and_is_raised(self, queue: JobQueue):
        submission = queue.submit(_request())
        with pytest.raises(RuntimeError, match="boom"):
            process_next(queue, "w1", _access, run=Engine(RuntimeError("boom")))
        status = queue.status(submission.run_id)
        assert status.status is FAILED and status.last_error["retryable"] is False

    def test_a_result_for_another_specification_is_not_stored(
        self, queue: JobQueue, store: SqlEvidenceStore, completed
    ):
        submission = queue.submit(_request())
        wrong = completed.model_copy(update={"spec_hash": "0" * 32})

        assert process_next(queue, "w1", _access, run=Engine(wrong)) is FAILED
        assert store.by_run_id(submission.run_id) is None
        assert "does not belong" in queue.status(submission.run_id).last_error["reason"]


# --- spec_hash: cache and de-duplication ----------------------------------------


class TestCacheAndDeduplication:
    def test_a_stored_result_answers_without_recomputing(
        self, queue: JobQueue, sessions, completed
    ):
        first = queue.submit(_request())
        engine = Engine(completed)
        process_next(queue, "w1", _access, run=engine)

        again = queue.submit(_request())

        assert (again.run_id, again.status, again.from_cache) == (first.run_id, SUCCEEDED, True)
        assert process_next(queue, "w1", _access, run=engine) is None
        assert engine.calls == 1
        assert _count(sessions, AnalysisRunRow) == _count(sessions, JobRow) == 1

    def test_a_refusal_is_a_cached_answer_too(self, queue: JobQueue, refused):
        first = queue.submit(_request(min_donors=500))
        process_next(queue, "w1", _access, run=Engine(refused))
        assert queue.submit(_request(min_donors=500)).run_id == first.run_id

    def test_a_result_from_another_engine_version_is_not_reused(
        self, queue: JobQueue, sessions, clock, completed
    ):
        first = queue.submit(_request())
        process_next(queue, "w1", _access, run=Engine(completed))

        newer = JobQueue(sessions, clock=clock, engine_version="99.0.0")
        again = newer.submit(_request())
        assert not again.from_cache and again.run_id != first.run_id

    def test_a_failed_run_is_not_a_cached_answer(self, queue: JobQueue, completed):
        first = queue.submit(_request())
        process_next(
            queue, "w1", _access, run=Engine(_engine_error(completed, ErrorCode.INTERNAL_ERROR))
        )
        again = queue.submit(_request())
        assert not again.from_cache and again.run_id != first.run_id

    def test_an_identical_request_in_flight_is_the_same_job(self, queue: JobQueue, sessions):
        first = queue.submit(_request())
        second = queue.submit(_request())
        assert (second.run_id, second.status, second.deduplicated) == (first.run_id, QUEUED, True)

        queue.claim("w1")
        third = queue.submit(_request())
        assert (third.run_id, third.status) == (first.run_id, RUNNING)
        assert _count(sessions, JobRow) == 1

    def test_a_cancelled_job_is_not_reused(self, queue: JobQueue):
        first = queue.submit(_request())
        queue.cancel(first.run_id)
        again = queue.submit(_request())
        assert again.run_id != first.run_id and again.status is QUEUED

    def test_a_different_specification_is_a_different_job(self, queue: JobQueue):
        assert queue.submit(_request(seed=1)).run_id != queue.submit(_request(seed=2)).run_id

    def test_an_unstored_case_is_refused(self, queue: JobQueue, sessions):
        request = get_case("southern-cardamom-redd").to_request()
        with pytest.raises(UnknownCaseError):
            queue.submit(request)
        assert _count(sessions, AnalysisRunRow) == 0


# --- claiming -------------------------------------------------------------------


class TestClaim:
    def test_oldest_available_first(self, queue: JobQueue, clock: FakeClock):
        ids = []
        for seed in (3, 1, 2):
            ids.append(queue.submit(_request(seed=seed)).run_id)
            clock.tick()
        assert [queue.claim("w1").run_id for _ in ids] == ids
        assert queue.claim("w1") is None

    def test_the_claimed_request_is_exactly_what_was_submitted(self, queue: JobQueue):
        request = _request(seed=7)
        queue.submit(request, requested_by="bhumi")
        job = queue.claim("w1")
        assert job.request == request and job.request.spec_hash == request.spec_hash
        assert (job.worker_id, job.attempt) == ("w1", 1)

    def test_an_empty_queue_claims_nothing(self, queue: JobQueue):
        assert queue.claim("w1") is None

    def test_a_queued_run_has_no_result_yet(self, queue: JobQueue, store: SqlEvidenceStore):
        submission = queue.submit(_request())
        assert store.by_run_id(submission.run_id) is None
        queue.claim("w1")
        assert store.by_run_id(submission.run_id) is None

    @pytest.mark.parametrize("damage", ["changed", "missing"])
    def test_an_unusable_stored_request_fails_and_the_next_job_is_claimed(
        self, queue: JobQueue, sessions, clock: FakeClock, damage: str
    ):
        bad = queue.submit(_request(seed=1))
        clock.tick()
        good = queue.submit(_request(seed=2))
        with sessions.begin() as session:
            run = session.get(AnalysisRunRow, bad.run_id)
            run.request = None if damage == "missing" else {**run.request, "seed": 999}

        assert queue.claim("w1").run_id == good.run_id
        status = queue.status(bad.run_id)
        assert status.status is FAILED and status.last_error["reason"] == "unusable-request"

    def test_two_claimers_that_pick_the_same_job_cannot_both_win(
        self, queue: JobQueue, monkeypatch
    ):
        """The interleaving PostgreSQL can produce, forced deterministically.

        Both claimers are made to choose the same candidate (as two transactions can
        before either commits). The status re-check in the UPDATE lets only one win.
        """
        target = queue.submit(_request()).run_id
        monkeypatch.setattr(JobQueue, "_candidate", lambda self, now: sa.literal(target))

        first = queue.claim("a")
        second = queue.claim("b")

        assert first is not None and first.run_id == target
        assert second is None
        status = queue.status(target)
        assert (status.status, status.locked_by, status.attempts) == (RUNNING, "a", 1)

    def test_the_claim_locks_and_skips_on_postgresql(self, queue: JobQueue):
        statement = queue._claim_statement(T0)
        pg = str(statement.compile(dialect=postgresql.dialect()))
        assert "FOR UPDATE OF jobs SKIP LOCKED" in pg
        assert "RETURNING analysis_runs.run_id" in pg
        assert "FOR UPDATE" not in str(statement.compile(dialect=sqlite.dialect()))


class TestConcurrentClaims:
    """Several threads claiming at once. Bounded waits only; no sleeps for timing."""

    N_WORKERS = 4
    N_JOBS = 20

    def test_each_job_is_claimed_exactly_once(self, queue: JobQueue, sessions, clock):
        submitted = [queue.submit(_request(seed=s)).run_id for s in range(1, self.N_JOBS + 1)]
        barrier = threading.Barrier(self.N_WORKERS, timeout=30)
        claims: list[tuple[str, str]] = []
        errors: list[BaseException] = []
        lock = threading.Lock()

        def work(worker_id: str) -> None:
            try:
                worker_queue = JobQueue(sessions, clock=clock)
                barrier.wait()
                while (job := worker_queue.claim(worker_id)) is not None:
                    with lock:
                        claims.append((job.run_id, worker_id))
            except BaseException as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=work, args=(f"w{i}",), daemon=True)
            for i in range(self.N_WORKERS)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)

        assert not [t for t in threads if t.is_alive()], "a worker did not finish"
        assert not errors, errors
        claimed = [run_id for run_id, _ in claims]
        assert sorted(claimed) == sorted(submitted)
        assert len(set(claimed)) == len(claimed), "a job was claimed twice"
        for run_id, worker_id in claims:
            row = _job(sessions, run_id)
            assert (row.attempts, row.locked_by) == (1, worker_id)


# --- leases ---------------------------------------------------------------------


class TestLeases:
    def test_a_heartbeat_extends_the_lease(self, queue: JobQueue, clock: FakeClock):
        submission = queue.submit(_request())
        job = queue.claim("w1")
        assert queue.status(submission.run_id).lease_expires_at == T0 + DEFAULT_LEASE

        clock.tick(timedelta(minutes=2))
        assert queue.heartbeat(job) is False
        assert queue.status(submission.run_id).lease_expires_at == clock.now + DEFAULT_LEASE

    def test_a_heartbeat_reports_a_cancel_request(self, queue: JobQueue):
        submission = queue.submit(_request())
        job = queue.claim("w1")
        queue.cancel(submission.run_id)
        assert queue.heartbeat(job) is True

    def test_an_expired_lease_returns_the_job_to_the_queue(self, queue: JobQueue, clock: FakeClock):
        submission = queue.submit(_request())
        queue.claim("w1")

        clock.tick(DEFAULT_LEASE + timedelta(seconds=1))
        assert queue.claim("w2") is None  # reaped, but backing off
        status = queue.status(submission.run_id)
        assert status.status is QUEUED and status.last_error["reason"] == "lease-expired"
        assert status.locked_by is None

        clock.tick(timedelta(seconds=30))
        job = queue.claim("w2")
        assert (job.run_id, job.attempt) == (submission.run_id, 2)

    def test_a_lease_inside_its_time_is_not_reaped(self, queue: JobQueue, clock: FakeClock):
        queue.submit(_request())
        queue.claim("w1")
        clock.tick(DEFAULT_LEASE - timedelta(seconds=1))
        assert queue.reap_expired() == 0

    def test_a_worker_that_lost_its_lease_cannot_write(
        self, queue: JobQueue, store: SqlEvidenceStore, clock: FakeClock, completed
    ):
        submission = queue.submit(_request())
        zombie = queue.claim("a")
        clock.tick(DEFAULT_LEASE + timedelta(seconds=1))
        assert queue.reap_expired() == 1
        clock.tick(timedelta(seconds=30))  # backoff runs from the moment it was reaped
        live = queue.claim("b")
        assert live is not None and live.attempt == 2

        with pytest.raises(LeaseLostError):
            queue.heartbeat(zombie)
        with pytest.raises(LeaseLostError):
            queue.complete(zombie, completed)
        assert store.by_run_id(submission.run_id) is None

        assert queue.complete(live, completed) is SUCCEEDED
        assert store.by_run_id(submission.run_id).run_id == submission.run_id

    def test_reclaiming_your_own_job_fences_your_old_attempt(
        self, queue: JobQueue, clock: FakeClock, completed
    ):
        queue.submit(_request())
        old = queue.claim("a")
        clock.tick(DEFAULT_LEASE + timedelta(seconds=1))
        assert queue.reap_expired() == 1
        clock.tick(timedelta(seconds=30))
        new = queue.claim("a")

        assert (old.attempt, new.attempt) == (1, 2)
        with pytest.raises(LeaseLostError):
            queue.complete(old, completed)
        assert queue.complete(new, completed) is SUCCEEDED

    def test_an_expired_lease_with_no_attempts_left_fails(self, sessions, store, clock: FakeClock):
        queue = JobQueue(sessions, clock=clock, max_attempts=1)
        submission = queue.submit(_request())
        queue.claim("w1")
        clock.tick(DEFAULT_LEASE + timedelta(seconds=1))

        assert queue.reap_expired() == 1
        status = queue.status(submission.run_id)
        assert status.status is FAILED and status.last_error["reason"] == "lease-expired"

    def test_an_expired_lease_on_a_cancelled_job_cancels_it(
        self, queue: JobQueue, clock: FakeClock
    ):
        submission = queue.submit(_request())
        queue.claim("w1")
        queue.cancel(submission.run_id)
        clock.tick(DEFAULT_LEASE + timedelta(seconds=1))

        queue.reap_expired()
        assert queue.status(submission.run_id).status is CANCELLED


# --- cancellation ---------------------------------------------------------------


class TestCancellation:
    def test_a_queued_job_is_cancelled_at_once(self, queue: JobQueue):
        submission = queue.submit(_request())
        assert queue.cancel(submission.run_id) is CANCELLED
        assert queue.claim("w1") is None

    def test_a_running_job_is_cancelled_at_its_next_checkpoint(self, queue: JobQueue):
        submission = queue.submit(_request())
        job = queue.claim("w1")
        assert queue.cancel(submission.run_id) is RUNNING  # requested, not yet honoured

        with pytest.raises(JobCancelledError, match="before-engine"):
            queue.checkpoint(job, "before-engine")
        assert queue.status(submission.run_id).status is CANCELLED

    def test_cancelling_twice_is_harmless(self, queue: JobQueue):
        submission = queue.submit(_request())
        queue.claim("w1")
        assert queue.cancel(submission.run_id) is RUNNING
        assert queue.cancel(submission.run_id) is RUNNING
        queued = queue.submit(_request(seed=5))
        assert queue.cancel(queued.run_id) is CANCELLED
        assert queue.cancel(queued.run_id) is CANCELLED

    def test_a_finished_job_cannot_be_cancelled(self, queue: JobQueue, completed):
        submission = queue.submit(_request())
        process_next(queue, "w1", _access, run=Engine(completed))
        with pytest.raises(IllegalTransitionError):
            queue.cancel(submission.run_id)

    def test_an_unknown_run_cannot_be_cancelled(self, queue: JobQueue):
        with pytest.raises(JobNotFoundError):
            queue.cancel("run_doesnotexist000")

    def test_cancel_before_data_access_runs_nothing(self, queue: JobQueue, monkeypatch, completed):
        submission = queue.submit(_request())
        claim = queue.claim

        def claim_then_cancel(worker_id):
            job = claim(worker_id)
            queue.cancel(job.run_id)
            return job

        monkeypatch.setattr(queue, "claim", claim_then_cancel)
        resolved: list[str] = []
        engine = Engine(completed)

        status = process_next(queue, "w1", lambda r: resolved.append("x") or _access(r), run=engine)

        assert status is CANCELLED and not resolved and engine.calls == 0
        assert queue.status(submission.run_id).last_error["stage"] == "before-data"

    def test_cancel_before_the_engine_skips_it(self, queue: JobQueue, completed):
        submission = queue.submit(_request())
        engine = Engine(completed)

        def resolve_then_cancel(request):
            queue.cancel(submission.run_id)
            return _access(request)

        assert process_next(queue, "w1", resolve_then_cancel, run=engine) is CANCELLED
        assert engine.calls == 0
        assert queue.status(submission.run_id).last_error["stage"] == "before-engine"

    def test_cancel_while_the_engine_runs_discards_its_result(
        self, queue: JobQueue, store: SqlEvidenceStore, sessions, completed
    ):
        submission = queue.submit(_request())
        engine = Engine(completed, on_call=lambda: queue.cancel(submission.run_id))

        assert process_next(queue, "w1", _access, run=engine) is CANCELLED

        assert engine.calls == 1
        assert store.by_run_id(submission.run_id) is None
        assert _count(sessions, EvidenceBundleRow) == 0
        assert queue.status(submission.run_id).last_error["stage"] == "engine"


# --- restarts -------------------------------------------------------------------


class TestRestart:
    def test_a_queued_job_survives_a_restart(
        self, url, sessions, queue: JobQueue, clock, completed
    ):
        request = _request()
        submission = queue.submit(request)
        sessions.kw["bind"].dispose()  # the first process is gone

        after = _sessions(url)
        restarted = JobQueue(after, clock=clock)
        job = restarted.claim("new-process")

        assert job.run_id == submission.run_id and job.request == request
        assert restarted.complete(job, completed) is SUCCEEDED
        reread = SqlEvidenceStore(_sessions(url)).by_run_id(submission.run_id)
        assert reread.run_id == submission.run_id and reread.bundle == completed.bundle

    def test_a_job_whose_worker_died_is_picked_up_again(
        self, url, sessions, queue: JobQueue, clock: FakeClock
    ):
        submission = queue.submit(_request())
        queue.claim("dies")
        sessions.kw["bind"].dispose()

        restarted = JobQueue(_sessions(url), clock=clock)
        clock.tick(DEFAULT_LEASE + timedelta(seconds=1))
        assert restarted.claim("survivor") is None  # reaped; backing off
        clock.tick(timedelta(seconds=30))
        job = restarted.claim("survivor")
        assert (job.run_id, job.attempt) == (submission.run_id, 2)


# --- status ---------------------------------------------------------------------


class TestStatus:
    def test_an_unknown_run_has_no_status(self, queue: JobQueue):
        assert queue.status("run_doesnotexist000") is None

    def test_a_run_saved_without_a_job_has_no_job_fields(
        self, queue: JobQueue, store: SqlEvidenceStore, completed
    ):
        store.save_result(completed)
        status = queue.status(completed.run_id)
        assert status.status is SUCCEEDED and status.attempts is None
        assert status.cancel_requested is False


# --- schema and boundary --------------------------------------------------------


class TestMigration0003:
    def test_it_adds_and_removes_only_its_columns(self, url: str):
        def columns(table: str) -> set[str]:
            return {c["name"] for c in sa.inspect(create_db_engine(url)).get_columns(table)}

        migrate.upgrade(url)
        assert "request" in columns("analysis_runs")
        assert "lease_expires_at" in columns("jobs")
        migrate.downgrade(url, "0002")
        assert "request" not in columns("analysis_runs")
        assert "lease_expires_at" not in columns("jobs")
        assert "engine_contract_version" in columns("analysis_runs")
        migrate.upgrade(url)
        assert "lease_expires_at" in columns("jobs")


class TestBoundary:
    def test_the_job_layer_uses_only_the_engines_public_names(self):
        allowed = {"run_analysis", "describe_engine", "engine_ref", "ENGINE_VERSION"}
        offenders = []
        files = sorted(JOBS_DIR.rglob("*.py"))
        assert any(p.name == "queue.py" for p in files)  # the scan is not vacuous
        for path in files:
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
                    "groundtruth.engine"
                ):
                    if node.module != "groundtruth.engine":
                        offenders.append(f"{path.name}: {node.module}")
                    offenders += [
                        f"{path.name}: {a.name}" for a in node.names if a.name not in allowed
                    ]
        assert not offenders, offenders
