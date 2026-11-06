"""Contract parity of the Redis queue with ``JobControl``, on an in-memory fake Redis."""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from groundtruth.contracts.errors import DataUnavailableError
from groundtruth.contracts.identifiers import EngineRef, new_run_id
from groundtruth.contracts.request import AnalysisRequest
from groundtruth.contracts.result import (
    AnalysisError,
    AnalysisResult,
    AnalysisStatus,
    EngineStatus,
    ErrorCode,
)
from groundtruth.platform.cases.registry import get_case
from groundtruth.platform.jobs.interface import LIVE_STAGES, JobControl, JobStatus
from groundtruth.platform.jobs.lifecycle import IllegalTransitionError, JobNotFoundError
from groundtruth.platform.jobs.redis_queue import (
    RedisJobQueue,
    process_job,
    redis_url_from_env,
    select_job_control,
)

CASE = get_case("kariba-redd")


class FakeRedis:
    """Just enough of ``redis.Redis(decode_responses=True)`` for the queue."""

    def __init__(self) -> None:
        self.data: dict[str, str | dict[str, str]] = {}

    def hset(self, name: str, mapping: Mapping[str, str]) -> int:
        h = self.data.setdefault(name, {})
        assert isinstance(h, dict)
        h.update(mapping)
        return len(mapping)

    def hgetall(self, name: str) -> dict[str, str]:
        h = self.data.get(name, {})
        assert isinstance(h, dict)
        return dict(h)

    def set(self, name: str, value: str, nx: bool = False) -> bool | None:
        if nx and name in self.data:
            return None
        self.data[name] = value
        return True

    def get(self, name: str) -> str | None:
        v = self.data.get(name)
        return v if isinstance(v, str) else None

    def delete(self, *names: str) -> int:
        return sum(self.data.pop(n, None) is not None for n in names)


@pytest.fixture
def parts() -> tuple[RedisJobQueue, list[str]]:
    sent: list[str] = []
    return RedisJobQueue(FakeRedis(), sent.append), sent


def _request(seed: int = 20260101) -> AnalysisRequest:
    return CASE.to_request(seed=seed)


def _refusal(request: AnalysisRequest) -> AnalysisResult:
    return AnalysisResult(
        run_id=new_run_id(),
        case_id=request.case_id,
        spec_hash=request.spec_hash,
        status=EngineStatus.REFUSED,
        engine=EngineRef(engine_version="t", contract_version=request.contract_version),
        data_mode=request.data_mode,
        error=AnalysisError(code=ErrorCode.INSUFFICIENT_DATA, message="too sparse"),
    )


def _access(request: AnalysisRequest) -> object:
    return object()


def test_satisfies_job_control_protocol(parts: tuple[RedisJobQueue, list[str]]) -> None:
    queue: JobControl = parts[0]
    assert queue.status("run_missing") is None


def test_submit_enqueues_and_reports_queued(parts: tuple[RedisJobQueue, list[str]]) -> None:
    queue, sent = parts
    sub = queue.submit(CASE, _request())
    assert sub.status is AnalysisStatus.QUEUED and not sub.from_cache and not sub.deduplicated
    assert sent == [sub.run_id]
    st = queue.status(sub.run_id)
    assert isinstance(st, JobStatus) and st.status is AnalysisStatus.QUEUED
    assert st.attempts == 0 and st.stage is None and not st.terminal


def test_identical_request_is_deduplicated(parts: tuple[RedisJobQueue, list[str]]) -> None:
    queue, sent = parts
    first = queue.submit(CASE, _request())
    again = queue.submit(CASE, _request())
    assert again.deduplicated and again.run_id == first.run_id and len(sent) == 1
    assert queue.submit(CASE, _request(seed=7)).run_id != first.run_id


def test_stages_progress_and_refusal_succeeds_then_caches(
    parts: tuple[RedisJobQueue, list[str]],
) -> None:
    queue, _ = parts
    request = _request()
    run_id = queue.submit(CASE, request).run_id
    seen: list[str | None] = []

    def engine(req: AnalysisRequest, data: object) -> AnalysisResult:
        status = queue.status(run_id)
        assert status is not None
        seen.append(status.stage)
        return _refusal(req)

    outcome = process_job(queue, run_id, "w1", _access, run=engine)  # type: ignore[arg-type]
    assert outcome is AnalysisStatus.SUCCEEDED
    assert seen == ["engine"]
    st = queue.status(run_id)
    assert st is not None and st.status is AnalysisStatus.SUCCEEDED and st.terminal
    assert st.engine_status == "refused" and st.error is not None
    assert set(st.stage_log) == set(LIVE_STAGES)
    cached = queue.submit(CASE, request)
    assert cached.from_cache and cached.run_id == run_id


def test_cancel_queued_is_immediate_idempotent_and_frees_key(
    parts: tuple[RedisJobQueue, list[str]],
) -> None:
    queue, _ = parts
    run_id = queue.submit(CASE, _request()).run_id
    assert queue.cancel(run_id) is AnalysisStatus.CANCELLED
    assert queue.cancel(run_id) is AnalysisStatus.CANCELLED
    assert process_job(queue, run_id, "w1", _access) is None  # type: ignore[arg-type]
    assert queue.submit(CASE, _request()).run_id != run_id


def test_cancel_running_stops_at_checkpoint(parts: tuple[RedisJobQueue, list[str]]) -> None:
    queue, _ = parts
    run_id = queue.submit(CASE, _request()).run_id

    def resolve(req: AnalysisRequest) -> object:
        assert queue.cancel(run_id) is AnalysisStatus.RUNNING
        return object()

    def engine(req: AnalysisRequest, data: object) -> AnalysisResult:
        raise AssertionError("engine must not run after cancellation")

    outcome = process_job(queue, run_id, "w1", resolve, run=engine)  # type: ignore[arg-type]
    assert outcome is AnalysisStatus.CANCELLED
    st = queue.status(run_id)
    assert st is not None and st.cancel_requested and st.status is AnalysisStatus.CANCELLED


def test_cancel_errors(parts: tuple[RedisJobQueue, list[str]]) -> None:
    queue, _ = parts
    with pytest.raises(JobNotFoundError):
        queue.cancel("run_nope")
    run_id = queue.submit(CASE, _request()).run_id
    process_job(queue, run_id, "w1", _access, run=lambda r, d: _refusal(r))  # type: ignore[arg-type]
    with pytest.raises(IllegalTransitionError):
        queue.cancel(run_id)


def test_data_unavailable_retries_then_fails(parts: tuple[RedisJobQueue, list[str]]) -> None:
    queue, sent = parts
    run_id = queue.submit(CASE, _request()).run_id

    def down(req: AnalysisRequest) -> object:
        raise DataUnavailableError("outage")

    for _ in range(3):
        process_job(queue, run_id, "w1", down)  # type: ignore[arg-type]
    st = queue.status(run_id)
    assert st is not None and st.status is AnalysisStatus.FAILED and st.attempts == 3
    assert "data unavailable" in (st.failure_reason or "") and len(sent) == 3


def test_engine_crash_fails_without_retry_and_reraises(
    parts: tuple[RedisJobQueue, list[str]],
) -> None:
    queue, _ = parts
    run_id = queue.submit(CASE, _request()).run_id

    def boom(req: AnalysisRequest, data: object) -> AnalysisResult:
        raise RuntimeError("bug")

    with pytest.raises(RuntimeError):
        process_job(queue, run_id, "w1", _access, run=boom)  # type: ignore[arg-type]
    st = queue.status(run_id)
    assert st is not None and st.status is AnalysisStatus.FAILED and st.attempts == 1


def test_select_job_control_keeps_sql_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REDIS_URL", raising=False)
    sentinel = object()
    assert redis_url_from_env() is None
    assert select_job_control(lambda: sentinel) is sentinel
