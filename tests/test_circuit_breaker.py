"""Resilience (#48): timeouts on every external call, a circuit breaker per provider, and an
outage that degrades without serving simulated data or persisting a partial result.

Every provider here is a fake; nothing touches the network.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from groundtruth.contracts.errors import DataUnavailableError
from groundtruth.platform.cases.registry import get_case
from groundtruth.platform.datasets.resilience import (
    BREAKER_PROVIDERS,
    CircuitBreaker,
    CircuitOpenError,
    PermanentError,
    RetryPolicy,
    TransientError,
    shared_breaker,
)
from groundtruth.platform.datasets.session import EarthEngineSession
from groundtruth.platform.datasets.synthetic import simulation_pin
from groundtruth.platform.jobs import entrypoint, worker
from groundtruth.platform.jobs.queue import JobQueue
from groundtruth.platform.jobs.worker import Worker
from groundtruth.platform.metrics import PROVIDERS, REGISTRY
from groundtruth.platform.reports.providers import GeminiNarrator
from groundtruth.platform.store import migrate
from groundtruth.platform.store.database import create_db_engine, create_session_factory
from groundtruth.platform.store.sql import SqlEvidenceStore

sys.path.insert(0, str(Path(__file__).parent))
from test_earthengine import KEY_JSON


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _fail(exc: Exception) -> Any:
    def call() -> None:
        raise exc

    return call


# --- the breaker itself ----------------------------------------------------------------------


class TestCircuitBreaker:
    @pytest.fixture
    def clock(self) -> Clock:
        return Clock()

    @pytest.fixture
    def breaker(self, clock: Clock) -> CircuitBreaker:
        return CircuitBreaker("p", failure_threshold=5, cooldown_s=60, clock=clock)

    def test_it_opens_after_five_failures_in_a_row_and_stops_calling(self, breaker):
        for _ in range(5):
            with pytest.raises(TransientError):
                breaker.call(_fail(TransientError("down")))
        assert breaker.state == "open"
        calls: list[int] = []
        with pytest.raises(CircuitOpenError) as caught:
            breaker.call(lambda: calls.append(1))
        assert calls == []  # the provider was not touched: no retry storm
        assert 0 < caught.value.retry_after_s <= 60

    def test_a_success_resets_the_count(self, breaker):
        for _ in range(4):
            with pytest.raises(TransientError):
                breaker.call(_fail(TransientError("blip")))
        breaker.call(lambda: "ok")
        for _ in range(4):
            with pytest.raises(TransientError):
                breaker.call(_fail(TransientError("blip")))
        assert breaker.state == "closed"

    def test_permanent_errors_never_open_it(self, breaker):
        for _ in range(20):
            with pytest.raises(PermanentError):
                breaker.call(_fail(PermanentError("bad credentials")))
        assert breaker.state == "closed"

    def test_after_the_cooldown_one_trial_call_decides(self, breaker, clock):
        for _ in range(5):
            with pytest.raises(TransientError):
                breaker.call(_fail(TransientError("down")))
        clock.now += 60
        assert breaker.state == "half_open"
        assert breaker.call(lambda: "back") == "back"
        assert breaker.state == "closed"

    def test_a_failed_trial_opens_it_for_another_cooldown(self, breaker, clock):
        for _ in range(5):
            with pytest.raises(TransientError):
                breaker.call(_fail(TransientError("down")))
        clock.now += 61
        with pytest.raises(TransientError):
            breaker.call(_fail(TransientError("still down")))
        assert breaker.state == "open"
        with pytest.raises(CircuitOpenError):
            breaker.call(lambda: "never")

    def test_only_one_trial_at_a_time(self, breaker, clock):
        for _ in range(5):
            with pytest.raises(TransientError):
                breaker.call(_fail(TransientError("down")))
        clock.now += 60
        refused: list[Exception] = []

        def trial() -> str:
            try:
                breaker.call(lambda: "second")
            except CircuitOpenError as exc:
                refused.append(exc)
            return "first"

        assert breaker.call(trial) == "first"
        assert len(refused) == 1  # the second caller did not get through during the trial

    def test_each_provider_has_its_own_breaker_and_an_opening_is_counted(self):
        assert set(BREAKER_PROVIDERS) == set(PROVIDERS)
        gemini, anthropic = shared_breaker("gemini"), shared_breaker("anthropic")
        assert gemini is shared_breaker("gemini") and gemini is not anthropic
        before = REGISTRY.get_sample_value("gt_circuit_open_total", {"provider": "gemini"}) or 0
        for _ in range(5):
            with pytest.raises(TransientError):
                gemini.call(_fail(TransientError("down")))
        after = REGISTRY.get_sample_value("gt_circuit_open_total", {"provider": "gemini"})
        assert after == before + 1 and anthropic.state == "closed"


# --- Earth Engine: an outage is data_unavailable, fast, and never a fixture -------------------


class SignIn:
    def __init__(self, error: Exception | None = None) -> None:
        self.error, self.calls = error, 0

    def initialize(self, key: Any, project: str) -> None:
        self.calls += 1
        if self.error is not None:
            raise self.error


def _session(backend: SignIn) -> EarthEngineSession:
    return EarthEngineSession(
        credentials=SecretStr(KEY_JSON),
        project="test-project",
        backend=backend,
        retry_policy=RetryPolicy(max_attempts=2, delays_s=(0.0,)),
        sleep=lambda s: None,
    )


class TestEarthEngineOutage:
    def test_an_outage_trips_the_breaker_then_fails_fast_as_data_unavailable(self):
        session = _session(SignIn())
        attempts: list[int] = []

        def down() -> None:
            attempts.append(1)
            raise TransientError("503 Service Unavailable")

        for _ in range(5):
            with pytest.raises(DataUnavailableError, match="after 2 attempts"):
                session.call("reduce", down)
        assert len(attempts) == 10  # five calls, each with its own retries
        with pytest.raises(DataUnavailableError, match=r"not attempted.*circuit open"):
            session.call("reduce", down)
        assert len(attempts) == 10  # the sixth never reached Earth Engine

    def test_rejected_credentials_never_open_the_breaker(self):
        from groundtruth.contracts.errors import ConfigurationError

        session = _session(SignIn(PermanentError("invalid_grant")))
        for _ in range(8):
            with pytest.raises(ConfigurationError):
                session.call("sign-in", lambda: None)
        assert shared_breaker("earth_engine").state == "closed"


# --- no partial result, and never a fixture -------------------------------------------------


@pytest.fixture
def stack(tmp_path: Path) -> tuple[JobQueue, SqlEvidenceStore]:
    url = f"sqlite:///{tmp_path / 'r.db'}"
    migrate.upgrade(url)
    sessions = create_session_factory(create_db_engine(url))
    store = SqlEvidenceStore(sessions)
    store.upsert_case(get_case("kariba-redd"))
    return JobQueue(sessions), store


class TestDegradesWithoutPersistingOrFaking:
    def test_observed_data_during_an_outage_is_never_served_from_a_fixture(
        self, stack, monkeypatch
    ):
        queue, store = stack

        def never(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError("an observed job was given simulated data")

        monkeypatch.setattr(worker, "synthetic_access", never)
        request = get_case("kariba-redd").to_request(data_mode="observed", seed=20260101)
        run_id = queue.submit(request).run_id
        Worker(queue, poll_interval=0.01).run(exit_when_idle=True, max_jobs=1)
        status = queue.status(run_id)
        assert status is not None and status.status.value in ("queued", "failed")
        reason = f"{status.failure_reason or ''} {status.last_error or ''}"
        assert "data unavailable" in reason
        assert store.by_run_id(run_id) is None  # nothing stored

    def test_a_failure_mid_job_persists_nothing(self, stack):
        queue, store = stack
        request = get_case("kariba-redd").to_request(
            seed=20260101, datasets=(simulation_pin(0.06),)
        )
        run_id = queue.submit(request).run_id

        def engine_dies(request: Any, data: Any) -> Any:
            raise RuntimeError("the engine process died half way")

        Worker(queue, run=engine_dies, poll_interval=0.01).run(exit_when_idle=True, max_jobs=1)
        assert queue.status(run_id).status.value == "failed"
        assert store.by_run_id(run_id) is None  # no result, no bundle, nothing partial

    def test_a_breaker_open_during_data_is_a_retryable_data_unavailable(self, stack):
        queue, store = stack
        request = get_case("kariba-redd").to_request(
            seed=20260101, datasets=(simulation_pin(0.06),)
        )
        run_id = queue.submit(request).run_id

        def provider_down(request: Any) -> Any:
            raise DataUnavailableError(str(CircuitOpenError("earth_engine", 42)))

        Worker(queue, resolve_access=provider_down, poll_interval=0.01).run(
            exit_when_idle=True, max_jobs=1
        )
        status = queue.status(run_id)
        assert status.status.value == "queued"  # tried again later, with backoff
        assert status.available_at is not None and status.available_at > status.created_at
        assert "circuit open" in str(status.last_error)
        assert store.by_run_id(run_id) is None


# --- GenAI: an outage falls back or refuses, without waiting -----------------------------------


def _gemini(responses: list[int]) -> tuple[GeminiNarrator, list[int]]:
    seen: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        status = responses[min(len(seen), len(responses) - 1)]
        seen.append(status)
        return httpx.Response(status, json={"error": "x"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return GeminiNarrator(api_key="test-key", client=client), seen


class TestGenAiOutage:
    def test_a_down_provider_opens_its_breaker_and_later_calls_never_reach_it(self):
        narrator, seen = _gemini([503])
        for _ in range(5):
            with pytest.raises(httpx.HTTPStatusError):
                narrator.complete("system", "user")
        with pytest.raises(CircuitOpenError):
            narrator.complete("system", "user")
        assert len(seen) == 5

    def test_a_rejected_key_is_not_an_outage(self):
        narrator, seen = _gemini([401])
        for _ in range(8):
            with pytest.raises(httpx.HTTPStatusError):
                narrator.complete("system", "user")
        assert shared_breaker("gemini").state == "closed" and len(seen) == 8

    def test_the_inline_report_falls_back_and_the_export_refuses(self):
        from groundtruth.platform.api.exports import build_case_bundle
        from groundtruth.platform.reports.export_pipeline import (
            NarrationFailedError,
            build_export_report,
        )
        from groundtruth.platform.reports.narrative import generate_report

        bundle = build_case_bundle("kariba-redd")
        narrator, seen = _gemini([503])
        for _ in range(5):
            with pytest.raises(httpx.HTTPStatusError):
                narrator.complete("s", "u")
        report = generate_report(bundle, narrator=narrator)
        assert report.fell_back is True  # the deterministic report, labelled
        with pytest.raises(NarrationFailedError):
            build_export_report(bundle, narrator=narrator)
        assert len(seen) == 5  # neither waited on the provider


# --- timeouts on the infrastructure clients ---------------------------------------------------


class TestTimeouts:
    def test_redis_has_socket_and_connect_timeouts(self, monkeypatch):
        from groundtruth.platform.jobs import redis_queue

        captured: dict[str, Any] = {}

        class FakeRedis:
            @staticmethod
            def from_url(url: str, **kwargs: Any) -> object:
                captured.update(kwargs)
                return object()

        monkeypatch.setattr(
            redis_queue, "_require", lambda name: types.SimpleNamespace(Redis=FakeRedis)
        )
        redis_queue.connect("redis://localhost:6379/0")
        assert captured["socket_timeout"] == captured["socket_connect_timeout"] == 5.0

    def test_postgresql_has_a_connect_timeout_and_sqlite_is_unchanged(self, monkeypatch):
        import sqlalchemy as sa

        from groundtruth.platform.store import database

        captured: dict[str, Any] = {}
        real = sa.create_engine

        def capture(url: Any, **kwargs: Any) -> Any:
            captured[str(url).split(":")[0]] = kwargs
            return real("sqlite://")

        monkeypatch.setattr(database.sa, "create_engine", capture)
        database.create_db_engine("postgresql+psycopg://u:p@db/gt")
        assert captured["postgresql+psycopg"]["connect_args"]["connect_timeout"] == 10
        database.create_db_engine("sqlite://", connect_args={"timeout": 30})
        assert captured["sqlite"]["connect_args"] == {"timeout": 30}

    def test_s3_has_explicit_timeouts_and_bounded_retries(self, monkeypatch):
        from groundtruth.platform.storage.blob_store import S3StorageBackend

        captured: dict[str, Any] = {}

        class Config:
            def __init__(self, **kwargs: Any) -> None:
                captured.update(kwargs)

        boto3 = types.ModuleType("boto3")
        boto3.client = lambda *args, **kwargs: kwargs  # type: ignore[attr-defined]
        botocore = types.ModuleType("botocore")
        botocore_config = types.ModuleType("botocore.config")
        botocore_config.Config = Config  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "boto3", boto3)
        monkeypatch.setitem(sys.modules, "botocore", botocore)
        monkeypatch.setitem(sys.modules, "botocore.config", botocore_config)
        S3StorageBackend(bucket="b")._get_client()
        assert (captured["connect_timeout"], captured["read_timeout"]) == (5, 30)
        assert captured["retries"] == {"max_attempts": 3, "mode": "standard"}

    def test_genai_and_earth_engine_keep_their_timeouts(self):
        from groundtruth.platform.datasets.earthengine import DEADLINE_MS

        assert GeminiNarrator(api_key="k").timeout == 60.0
        assert DEADLINE_MS == 360_000


# --- the e2e pause flag is a testing aid, refused in production ---------------------------------


class TestPauseBeforeEngine:
    @staticmethod
    def _settings(monkeypatch: pytest.MonkeyPatch, app_env: str) -> None:
        settings = types.SimpleNamespace(
            database_url=None,
            git_sha=None,
            log_level="INFO",
            random_seed=20260101,
            worker_metrics_port=0,
            metrics_bind_address="127.0.0.1",
            app_env=app_env,
        )
        monkeypatch.setattr(entrypoint, "get_settings", lambda: settings)

    def test_it_is_off_by_default(self):
        assert entrypoint.build_parser().parse_args([]).pause_before_engine == 0.0

    def test_the_worker_refuses_to_start_with_it_in_production(self, monkeypatch, capsys):
        self._settings(monkeypatch, "production")
        code = entrypoint.main(["--pause-before-engine", "5"])
        assert code == entrypoint.EXIT_STARTUP_REFUSED
        assert "refused when APP_ENV=production" in capsys.readouterr().err

    def test_outside_production_it_is_accepted(self, monkeypatch, capsys):
        self._settings(monkeypatch, "development")
        entrypoint.main(["--pause-before-engine", "5"])  # stops later: no DATABASE_URL here
        err = capsys.readouterr().err
        assert "TESTING AID" in err and "refused when APP_ENV=production" not in err

    def test_a_job_cancelled_during_the_pause_ends_cancelled_with_nothing_stored(
        self, stack, monkeypatch
    ):
        queue, store = stack
        request = get_case("kariba-redd").to_request(
            seed=20260101, datasets=(simulation_pin(0.06),)
        )
        run_id = queue.submit(request).run_id
        # The cancel arrives while the job waits, as a person's click would.
        monkeypatch.setattr(entrypoint.time, "sleep", lambda s: queue.cancel(run_id))
        resolve = entrypoint.paused(worker.default_resolve_access(), 5)
        Worker(queue, resolve_access=resolve, poll_interval=0.01).run(
            exit_when_idle=True, max_jobs=1
        )
        assert queue.status(run_id).status.value == "cancelled"
        assert store.by_run_id(run_id) is None
