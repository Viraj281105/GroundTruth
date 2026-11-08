"""The background worker process (issue #25).

SQLite through the real migrations. The job layer runs on a fake clock, so leases and
backoff never wait on real time. Where a real thread is involved (the heartbeat), tests
synchronise on events with bounded waits; nothing sleeps to "give a thread time".
Everything here runs on SIMULATED DATA.
"""

from __future__ import annotations

import json
import logging
import os
import pathlib
import subprocess
import sys
import threading
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session, sessionmaker

from groundtruth import cli
from groundtruth.contracts.identifiers import new_run_id
from groundtruth.contracts.request import AnalysisRequest
from groundtruth.contracts.result import AnalysisResult, AnalysisStatus, EngineStatus
from groundtruth.engine import ENGINE_VERSION, run_analysis
from groundtruth.logging import ContextFilter, JsonFormatter, get_logger, log_context
from groundtruth.platform.cases.registry import get_case
from groundtruth.platform.datasets.access import synthetic_access
from groundtruth.platform.jobs import entrypoint, worker
from groundtruth.platform.jobs.entrypoint import ShutdownHandler, safe_database_url
from groundtruth.platform.jobs.lifecycle import DEFAULT_LEASE, LeaseLostError
from groundtruth.platform.jobs.queue import JobQueue
from groundtruth.platform.jobs.worker import Heartbeat, Worker, engine_runner
from groundtruth.platform.store import database, migrate
from groundtruth.platform.store import sql as store_sql
from groundtruth.platform.store.database import create_db_engine, create_session_factory
from groundtruth.platform.store.models import AnalysisRunRow, EvidenceBundleRow
from groundtruth.platform.store.sql import SqlEvidenceStore

QUEUED, RUNNING, SUCCEEDED, FAILED, CANCELLED = (
    AnalysisStatus.QUEUED,
    AnalysisStatus.RUNNING,
    AnalysisStatus.SUCCEEDED,
    AnalysisStatus.FAILED,
    AnalysisStatus.CANCELLED,
)
T0 = datetime(2026, 11, 1, 12, 0, 0, tzinfo=UTC)
WAIT = 30.0
"""Upper bound on any wait for another thread. Reached only if something is broken."""
REPO = pathlib.Path(__file__).resolve().parents[1]
SYNTHETIC_SOURCE = "groundtruth.platform.datasets.synthetic"
"""Provenance source of every value derived from the synthetic fixture."""


class FakeClock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now

    def tick(self, delta: timedelta) -> None:
        self.now += delta


class Crash(BaseException):
    """Stands in for the process dying: not an ``Exception``, so nothing catches it."""


class SpyQueue(JobQueue):
    """A real queue that also signals what its heartbeats saw."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.beat = threading.Event()
        self.cancel_seen = threading.Event()
        self.lost = threading.Event()
        self.fail_next_heartbeat = threading.Event()

    def heartbeat(self, job):
        if self.fail_next_heartbeat.is_set():
            self.fail_next_heartbeat.clear()
            raise sa.exc.OperationalError("SELECT 1", {}, Exception("database blip"))
        try:
            cancel = super().heartbeat(job)
        except LeaseLostError:
            self.lost.set()
            raise
        self.beat.set()
        if cancel:
            self.cancel_seen.set()
        return cancel


def _request(*, seed: int = 20260101) -> AnalysisRequest:
    return get_case("kariba-redd").to_request(seed=seed)


def _sessions(url: str) -> sessionmaker[Session]:
    return create_session_factory(create_db_engine(url, connect_args={"timeout": 30}))


@pytest.fixture(scope="module")
def completed() -> AnalysisResult:
    """A real completed engine run for ``_request()`` on SIMULATED DATA."""
    request = _request()
    return run_analysis(request, synthetic_access(request, true_effect=0.06))


def _replay(result: AnalysisResult, *, wait_for: threading.Event | None = None, before=None):
    """An engine stand-in: optionally act, optionally block (bounded), then return."""

    def run(request, data):
        if before is not None:
            before()
        if wait_for is not None:
            assert wait_for.wait(WAIT), "the engine stand-in waited too long"
        return result.model_copy(update={"run_id": new_run_id()})

    return run


@pytest.fixture
def url(tmp_path: pathlib.Path) -> str:
    return f"sqlite:///{tmp_path / 'worker.db'}"


@pytest.fixture
def sessions(url: str) -> sessionmaker[Session]:
    migrate.upgrade(url)
    sessions = _sessions(url)
    SqlEvidenceStore(sessions).upsert_case(get_case("kariba-redd"))
    return sessions


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def queue(sessions, clock) -> SpyQueue:
    return SpyQueue(sessions, clock=clock)


@pytest.fixture
def store(sessions, clock) -> SqlEvidenceStore:
    return SqlEvidenceStore(sessions, clock=clock)


class _Lines(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.lines: list[dict] = []
        self.addFilter(ContextFilter())
        self.setFormatter(JsonFormatter())

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(json.loads(self.format(record)))


@pytest.fixture
def logs():
    """Every log line as the worker would print it, parsed back from JSON."""
    root = logging.getLogger()
    handler, level = _Lines(), root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    yield handler.lines
    root.removeHandler(handler)
    root.setLevel(level)


@pytest.fixture
def keep_logging():
    """``main()`` reconfigures the root logger; put it back afterwards."""
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield
    for handler in list(root.handlers):
        root.removeHandler(handler)
    for handler in handlers:
        root.addHandler(handler)
    root.setLevel(level)


def _worker(queue, **kwargs) -> Worker:
    kwargs.setdefault("worker_id", "w-test")
    kwargs.setdefault("heartbeat_interval", 0.01)
    return Worker(queue, **kwargs)


def _heartbeats_alive() -> list[str]:
    return [t.name for t in threading.enumerate() if t.name.startswith("heartbeat-")]


def _bundles(sessions) -> int:
    with sessions() as session:
        return session.scalar(sa.select(sa.func.count()).select_from(EvidenceBundleRow))


# --- Kariba, end to end ---------------------------------------------------------


class TestKaribaEndToEnd:
    def test_kariba_runs_to_completion_with_full_provenance(self, queue, store, logs):
        submission = queue.submit(_request())

        processed = _worker(queue, run=engine_runner("abc1234")).run(exit_when_idle=True)

        assert processed == 1
        assert queue.status(submission.run_id).status is SUCCEEDED
        result = store.by_run_id(submission.run_id)
        assert result.status is EngineStatus.COMPLETED and result.bundle is not None
        assert (result.engine.engine_version, result.engine.git_sha) == (ENGINE_VERSION, "abc1234")
        # Full provenance: every item, complete and fingerprinted.
        assert len(result.bundle) > 10
        for item in result.bundle:
            assert item.provenance.source and item.provenance.method, item.id
            assert len(item.provenance.fingerprint()) == 16
        # Labelled simulated, in the result and in its provenance.
        assert result.is_simulated and result.data_mode == "simulated"
        assert any(i.provenance.source == SYNTHETIC_SOURCE for i in result.bundle)
        assert any(w.startswith("SIMULATED DATA") for w in result.bundle.warnings)
        # Logs carry run_id, case_id and stage through every step.
        job_lines = [line for line in logs if line.get("run_id") == submission.run_id]
        assert {line["stage"] for line in job_lines} >= {
            "claim",
            "data",
            "engine",
            "record",
            "done",
        }
        for line in job_lines:
            assert line["case_id"] == "kariba-redd" and line["data_mode"] == "simulated"
            assert line["worker_id"] == "w-test"
        # A job that finished normally must not be reported as a lost lease.
        assert not [line for line in logs if line["level"] in ("WARNING", "ERROR")
                    and line.get("run_id") == submission.run_id]  # fmt: skip

    def test_a_missing_git_sha_is_recorded_as_null_never_a_placeholder(self, queue, store):
        submission = queue.submit(_request())
        _worker(queue, run=engine_runner(None)).run(exit_when_idle=True)
        assert store.by_run_id(submission.run_id).engine.git_sha is None


# --- the heartbeat thread -------------------------------------------------------


class TestHeartbeat:
    def test_the_lease_is_kept_alive_while_the_engine_runs(self, queue, completed, logs):
        submission = queue.submit(_request())
        engine = _replay(completed, wait_for=queue.beat)  # returns only after a heartbeat

        status = _worker(queue, run=engine).run_job(queue.claim("w-test"))

        assert status is SUCCEEDED
        assert queue.status(submission.run_id).status is SUCCEEDED
        assert not _heartbeats_alive()
        assert not any("lease lost" in line["message"] for line in logs)

    def test_a_heartbeat_error_is_logged_and_beating_continues(self, queue, completed, logs):
        queue.submit(_request())
        queue.fail_next_heartbeat.set()
        engine = _replay(completed, wait_for=queue.beat)  # a later beat must still succeed

        assert _worker(queue, run=engine).run_job(queue.claim("w-test")) is SUCCEEDED
        assert any("heartbeat failed" in line["message"] for line in logs)

    def test_heartbeat_lines_carry_the_job_context(self, queue, completed, logs):
        submission = queue.submit(_request())
        queue.fail_next_heartbeat.set()
        _worker(queue, run=_replay(completed, wait_for=queue.beat)).run_job(queue.claim("w-test"))

        (line,) = [entry for entry in logs if "heartbeat failed" in entry["message"]]
        assert (line["run_id"], line["stage"]) == (submission.run_id, "heartbeat")

    def test_the_interval_must_be_positive(self, queue):
        queue.submit(_request())
        with pytest.raises(ValueError):
            Heartbeat(queue, queue.claim("w"), 0)


# --- cancellation mid-run -------------------------------------------------------


class TestCancellationMidRun:
    def test_a_cancel_during_the_engine_discards_its_result(
        self, queue, store, sessions, completed, logs
    ):
        submission = queue.submit(_request())
        engine = _replay(
            completed,
            before=lambda: queue.cancel(submission.run_id),
            wait_for=queue.cancel_seen,  # the heartbeat must notice before the engine returns
        )

        status = _worker(queue, run=engine).run_job(queue.claim("w-test"))

        assert status is CANCELLED
        assert store.by_run_id(submission.run_id) is None
        assert _bundles(sessions) == 0
        assert any("cancel requested" in line["message"] for line in logs)

    def test_a_cancel_before_the_engine_never_runs_it(self, queue, completed):
        submission = queue.submit(_request())
        ran: list[bool] = []
        job = queue.claim("w-test")
        queue.cancel(submission.run_id)

        status = _worker(queue, run=lambda r, d: ran.append(True) or completed).run_job(job)

        assert status is CANCELLED and not ran


# --- losing the lease mid-run ---------------------------------------------------


class TestLeaseLostMidRun:
    def test_a_worker_that_lost_its_job_writes_nothing(
        self, queue, store, sessions, clock, completed, logs
    ):
        submission = queue.submit(_request())
        thief = JobQueue(sessions, clock=clock)

        def another_worker_takes_over():
            clock.tick(DEFAULT_LEASE + timedelta(seconds=1))
            while thief.reap_expired() == 0:
                clock.tick(DEFAULT_LEASE + timedelta(seconds=1))
            clock.tick(timedelta(seconds=30))
            assert thief.claim("thief") is not None

        engine = _replay(completed, before=another_worker_takes_over, wait_for=queue.lost)

        assert _worker(queue, run=engine).run_job(queue.claim("w-test")) is None

        assert store.by_run_id(submission.run_id) is None
        status = queue.status(submission.run_id)
        assert (status.status, status.locked_by, status.attempts) == (RUNNING, "thief", 2)
        assert any("lost the job" in line["message"] for line in logs)


# --- a crash leaves no partial result -------------------------------------------


class TestCrashLeavesNoPartialResult:
    def test_a_crash_during_the_engine(self, queue, store, sessions, clock, completed):
        submission = queue.submit(_request())

        def crash(request, data):
            raise Crash

        with pytest.raises(Crash):
            _worker(queue, run=crash).run(exit_when_idle=True)

        assert queue.status(submission.run_id).status is RUNNING  # still claimed
        assert store.by_run_id(submission.run_id) is None
        assert _bundles(sessions) == 0
        assert not _heartbeats_alive()

        # The lease expires and the job is run again, by a new worker.
        clock.tick(DEFAULT_LEASE + timedelta(seconds=1))
        queue.reap_expired()
        clock.tick(timedelta(seconds=30))
        assert _worker(queue, run=_replay(completed)).run(exit_when_idle=True) == 1
        status = queue.status(submission.run_id)
        assert (status.status, status.attempts) == (SUCCEEDED, 2)

    def test_a_crash_in_the_middle_of_writing_the_result(
        self, queue, store, sessions, completed, monkeypatch
    ):
        """The run's result columns were already set when the crash came; none survive."""
        submission = queue.submit(_request())

        def crash_before_the_bundle(result, written_at):
            raise Crash

        monkeypatch.setattr(store_sql, "_bundle_row", crash_before_the_bundle)
        with pytest.raises(Crash):
            _worker(queue, run=_replay(completed)).run(exit_when_idle=True)

        with sessions() as session:
            run = session.get(AnalysisRunRow, submission.run_id)
            assert (run.status, run.engine_status, run.engine_version) == ("running", None, None)
        assert store.by_run_id(submission.run_id) is None
        assert _bundles(sessions) == 0


# --- a bad job does not stop the worker -----------------------------------------


class TestKeepsRunning:
    def test_a_bug_fails_that_job_and_the_next_job_still_runs(self, queue, clock, completed, logs):
        first = queue.submit(_request(seed=1))
        clock.tick(timedelta(seconds=1))
        second = queue.submit(_request())
        outcomes = iter([RuntimeError("estimator exploded"), completed])

        def engine(request, data):
            outcome = next(outcomes)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome.model_copy(update={"run_id": new_run_id()})

        assert _worker(queue, run=engine).run(exit_when_idle=True) == 2

        assert queue.status(first.run_id).status is FAILED
        assert queue.status(second.run_id).status is SUCCEEDED
        (error,) = [line for line in logs if line["level"] == "ERROR"]
        assert error["run_id"] == first.run_id and "estimator exploded" in error["exception"]

    def test_an_unreachable_database_is_retried_not_fatal(
        self, queue, completed, monkeypatch, logs
    ):
        queue.submit(_request())
        real_claim = queue.claim
        failures = iter([True, True])

        def flaky_claim(worker_id):
            if next(failures, False):
                raise sa.exc.OperationalError("SELECT", {}, Exception("connection refused"))
            return real_claim(worker_id)

        monkeypatch.setattr(queue, "claim", flaky_claim)
        processed = _worker(queue, run=_replay(completed), db_retry_initial=0.001).run(
            exit_when_idle=True
        )

        assert processed == 1
        assert sum("database unavailable" in line["message"] for line in logs) == 2


# --- stopping -------------------------------------------------------------------


class TestShutdown:
    def test_the_first_signal_finishes_the_current_job_and_claims_no_more(
        self, queue, clock, completed
    ):
        first = queue.submit(_request(seed=1))
        clock.tick(timedelta(seconds=1))
        second = queue.submit(_request(seed=2))
        w = _worker(queue)
        handler = ShutdownHandler(w)
        w._run = _replay(completed.model_copy(update={"spec_hash": _request(seed=1).spec_hash}),
                         before=lambda: handler(2, None))  # fmt: skip

        assert w.run() == 1

        assert queue.status(first.run_id).status is SUCCEEDED
        assert queue.status(second.run_id).status is QUEUED

    def test_the_second_signal_stops_at_once(self, queue):
        handler = ShutdownHandler(_worker(queue))
        handler(2, None)
        with pytest.raises(KeyboardInterrupt):
            handler(2, None)

    def test_an_idle_worker_wakes_as_soon_as_it_is_stopped(self, queue):
        w = _worker(queue, poll_interval=3600)  # would wait an hour if it slept
        done = threading.Event()
        thread = threading.Thread(target=lambda: (w.run(), done.set()), daemon=True)
        thread.start()
        w.request_stop()
        assert done.wait(WAIT)

    def test_max_jobs_stops_after_that_many(self, queue, clock, completed):
        for seed in (1, 2):
            queue.submit(_request(seed=seed))
            clock.tick(timedelta(seconds=1))

        def engine(request, data):
            return completed.model_copy(
                update={"run_id": new_run_id(), "spec_hash": request.spec_hash}
            )

        assert _worker(queue, run=engine).run(max_jobs=1) == 1


# --- startup --------------------------------------------------------------------


def _configure(monkeypatch, *, url: str | None, git_sha: str | None = "abc1234") -> None:
    settings = SimpleNamespace(
        database_url=url, git_sha=git_sha, log_level="INFO", random_seed=20260101
    )
    for module in (database, entrypoint, cli):
        monkeypatch.setattr(module, "get_settings", lambda: settings)


@pytest.mark.usefixtures("keep_logging")
class TestStartup:
    def test_no_database_url_refuses_to_start(self, monkeypatch, capsys):
        _configure(monkeypatch, url=None)
        assert entrypoint.main([]) == entrypoint.EXIT_STARTUP_REFUSED
        assert "DATABASE_URL" in capsys.readouterr().err

    def test_an_unmigrated_database_refuses_to_start(self, monkeypatch, capsys, url):
        _configure(monkeypatch, url=url)
        assert entrypoint.main(["--exit-when-idle"]) == entrypoint.EXIT_STARTUP_REFUSED
        err = capsys.readouterr().err
        assert "--migrate" in err and migrate.head_revision() in err

    def test_migrate_applies_the_migrations_then_runs(self, monkeypatch, url):
        _configure(monkeypatch, url=url)
        assert entrypoint.main(["--migrate", "--exit-when-idle"]) == entrypoint.EXIT_OK
        assert migrate.is_at_head(url)

    def test_a_missing_git_sha_is_warned_about(self, monkeypatch, capsys, sessions, url):
        _configure(monkeypatch, url=url, git_sha=None)
        assert entrypoint.main(["--exit-when-idle"]) == entrypoint.EXIT_OK
        # Only the JSON lines are the worker's. Another test module can leave a logging
        # handler on a closed stream, whose "--- Logging error ---" text lands here too.
        err = capsys.readouterr().err
        lines = [json.loads(line) for line in err.splitlines() if line.startswith("{")]
        assert any("GIT_SHA is not set" in line["message"] for line in lines)
        assert any("SIMULATED DATA" in line["message"] for line in lines)

    def test_signal_handlers_are_restored_afterwards(self, monkeypatch, sessions, url):
        import signal

        before = signal.getsignal(signal.SIGINT)
        _configure(monkeypatch, url=url)
        entrypoint.main(["--exit-when-idle"])
        assert signal.getsignal(signal.SIGINT) is before

    def test_a_blank_git_sha_means_unknown(self, monkeypatch):
        from groundtruth.platform.config import Settings

        monkeypatch.setenv("GIT_SHA", "   ")
        assert Settings().git_sha is None
        monkeypatch.setenv("GIT_SHA", "deadbeef")
        assert Settings().git_sha == "deadbeef"


# --- logging --------------------------------------------------------------------


class TestLogging:
    def test_a_password_in_the_database_url_is_never_logged(self):
        safe = safe_database_url("postgresql+psycopg://bhumi:s3cr3t-pw@db.example/groundtruth")
        assert "s3cr3t-pw" not in safe and "bhumi" in safe and "db.example" in safe

    def test_the_engines_own_log_lines_carry_the_job_context(self, logs):
        engine_logger = get_logger("uncertainty.placebo")  # the engine's logger name
        with log_context(run_id="run_0000000000000001", case_id="kariba-redd", stage="engine"):
            engine_logger.debug("placebo fit failed for donor-07")
        (line,) = [entry for entry in logs if "donor-07" in entry["message"]]
        assert (line["run_id"], line["case_id"], line["stage"]) == (
            "run_0000000000000001",
            "kariba-redd",
            "engine",
        )

    def test_context_nests_and_an_explicit_field_wins(self, logs):
        log = get_logger("test")
        with log_context(run_id="run_a", stage="data"):
            with log_context(stage="engine"):
                log.info("inner")
            log.info("outer", extra={"stage": "explicit"})
        log.info("after")
        inner, outer, after = (
            next(e for e in logs if e["message"] == m) for m in ("inner", "outer", "after")
        )
        assert (inner["run_id"], inner["stage"]) == ("run_a", "engine")
        assert outer["stage"] == "explicit"
        assert "run_id" not in after


# --- the CLI --------------------------------------------------------------------


@pytest.mark.usefixtures("keep_logging")
class TestCli:
    def test_submit_then_job_shows_a_simulated_queued_run(self, monkeypatch, capsys, sessions, url):
        _configure(monkeypatch, url=url)
        assert cli.main(["submit", "kariba-redd", "--synthetic", "--json"]) == 0
        submission = json.loads(capsys.readouterr().out)
        assert submission["status"] == "queued"

        assert cli.main(["job", submission["run_id"]]) == 0
        out = capsys.readouterr().out
        assert "SIMULATED DATA" in out and "queued" in out and "simulated" in out

    def test_submit_requires_synthetic(self, monkeypatch, url):
        _configure(monkeypatch, url=url)
        assert cli.main(["submit", "kariba-redd"]) == 2

    def test_commands_refuse_an_unmigrated_database(self, monkeypatch, capsys, url):
        _configure(monkeypatch, url=url)
        assert cli.main(["submit", "kariba-redd", "--synthetic"]) == 2
        assert "--migrate" in capsys.readouterr().err

    def test_an_unknown_run(self, monkeypatch, sessions, url):
        _configure(monkeypatch, url=url)
        assert cli.main(["job", "run_doesnotexist000"]) == 1


# --- the real entrypoint, as a process ------------------------------------------


class TestEntrypointProcess:
    def test_the_worker_command_runs_kariba_and_logs_json(self, sessions, url, tmp_path):
        """``python -m apps.worker.main`` as you would start it, on a real Kariba job."""
        submission = JobQueue(sessions).submit(_request())
        env = {**os.environ, "DATABASE_URL": url, "GIT_SHA": "deadbeef", "PYTHONUTF8": "1"}

        proc = subprocess.run(
            [sys.executable, "-m", "apps.worker.main", "--exit-when-idle"],
            cwd=REPO,
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
        )

        assert proc.returncode == 0, proc.stderr
        result = SqlEvidenceStore(_sessions(url)).by_run_id(submission.run_id)
        assert result is not None and result.status is EngineStatus.COMPLETED
        assert result.engine.git_sha == "deadbeef" and result.is_simulated
        lines = [json.loads(line) for line in proc.stderr.splitlines() if line.startswith("{")]
        assert any(
            line.get("run_id") == submission.run_id and line.get("stage") == "done"
            for line in lines
        )
        assert lines[-1]["message"] == "worker stopped after 1 job(s)"

    def test_the_worker_module_is_importable_without_running(self):
        assert worker.DEFAULT_TRUE_EFFECT == 0.06
