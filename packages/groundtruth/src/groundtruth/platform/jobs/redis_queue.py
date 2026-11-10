"""A Redis/arq backed job queue behind the same :class:`JobControl` interface.

**Optional.** The default queue stays the SQL one. This backend is chosen only when a
maintainer wires :func:`select_job_control` in (see ``docs/queue-backends.md``) and
``REDIS_URL`` is set. ``redis`` and ``arq`` are imported lazily, so importing this module
needs neither.

State lives in one Redis hash per run (``gt:job:<run_id>``); an arq worker executes
:func:`run_job`. Per-stage progress (``claim, data, engine, record``) is written to the
hash as each stage begins, so ``status`` reports the live stage and ``stage_log``.

Deduplication and caching use ``gt:spec:<spec_hash>``, set with ``SET NX``: an identical
request that is queued or running returns that job (``deduplicated``); one that already
succeeded returns its result (``from_cache``). A failed or cancelled run frees the key.

Known limits, stated rather than hidden: transitions are read-modify-write rather than
Lua scripts, so a cancel racing the worker's claim can lose by one stage, and there is no
lease fencing (arq's job timeout and retry cover a dead worker). The Redis path stores
the full request, so it does not write the case to the SQL case store.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import os
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any, Protocol

from groundtruth.contracts.errors import DataUnavailableError
from groundtruth.contracts.identifiers import new_run_id
from groundtruth.contracts.request import AnalysisRequest
from groundtruth.contracts.result import AnalysisResult, AnalysisStatus
from groundtruth.engine import run_analysis
from groundtruth.platform.cases.registry import CaseDefinition
from groundtruth.platform.jobs.interface import LIVE_STAGES, JobStatus, Lane, Submission
from groundtruth.platform.jobs.lifecycle import (
    IllegalTransitionError,
    JobCancelledError,
    JobNotFoundError,
)
from groundtruth.platform.jobs.runner import ResolveAccess, RunEngine

JOB_PREFIX = "gt:job:"
SPEC_PREFIX = "gt:spec:"
DEFAULT_MAX_ATTEMPTS = 3
_QUEUED, _RUNNING = AnalysisStatus.QUEUED, AnalysisStatus.RUNNING


class RedisLike(Protocol):
    """The slice of ``redis.Redis(decode_responses=True)`` this module uses."""

    def hset(self, name: str, mapping: Mapping[str, str]) -> Any: ...
    def hgetall(self, name: str) -> dict[str, str]: ...
    def set(self, name: str, value: str, nx: bool = False) -> Any: ...
    def get(self, name: str) -> str | None: ...
    def delete(self, *names: str) -> Any: ...


Enqueue = Callable[[str], None]
"""Hands a ``run_id`` to the worker pool. Production: arq. Tests: a list append."""


def redis_url_from_env() -> str | None:
    """``REDIS_URL`` if set and non-empty, else ``None`` (meaning: keep the SQL queue)."""
    return os.environ.get("REDIS_URL") or None


def _require(module: str) -> Any:
    try:
        return importlib.import_module(module)
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise ImportError(
            f"the Redis queue backend needs the {module.split('.')[0]!r} package; "
            "install it with: pip install redis arq"
        ) from exc


REDIS_TIMEOUT_S = 5.0
"""Connecting to Redis, and each command, gives up after this long (#48): a Redis that stops
answering must fail the request, not hang the API or a worker forever."""


def connect(url: str) -> RedisLike:
    """A synchronous Redis client that returns ``str`` values, with timeouts."""
    client: RedisLike = _require("redis").Redis.from_url(
        url,
        decode_responses=True,
        socket_timeout=REDIS_TIMEOUT_S,
        socket_connect_timeout=REDIS_TIMEOUT_S,
    )
    return client


def arq_enqueue(url: str) -> Enqueue:
    """An :data:`Enqueue` that schedules :func:`run_job` on an arq worker."""
    arq = _require("arq")
    settings = _require("arq.connections").RedisSettings.from_dsn(url)

    def enqueue(run_id: str) -> None:
        async def go() -> None:
            pool = await arq.create_pool(settings)
            try:
                await pool.enqueue_job("run_job", run_id)
            finally:
                await pool.aclose()

        asyncio.run(go())

    return enqueue


def _now() -> datetime:
    return datetime.now(UTC)


def _opt_dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class RedisJobQueue:
    """Implements :class:`JobControl` over Redis. Construct with a client and an enqueuer."""

    def __init__(
        self,
        client: RedisLike,
        enqueue: Enqueue,
        *,
        clock: Callable[[], datetime] = _now,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ) -> None:
        self._r = client
        self._enqueue = enqueue
        self._clock = clock
        self._max_attempts = max_attempts

    @classmethod
    def from_url(cls, url: str) -> RedisJobQueue:
        """The production wiring: real Redis plus arq."""
        return cls(connect(url), arq_enqueue(url))

    # -- JobControl -------------------------------------------------------------------

    def submit(
        self,
        case: CaseDefinition,
        request: AnalysisRequest,
        *,
        requested_by: str | None = None,
        project_id: str | None = None,
        lane: Lane = "batch",
    ) -> Submission:
        """Queue ``request``, or return its cached result or the identical in-flight job.

        This queue has no lanes: ``lane`` is accepted for the common interface and every job
        is first in, first out. Lanes are a feature of the SQL queue (#47).
        """
        spec_key = SPEC_PREFIX + request.spec_hash
        run_id = new_run_id()
        if not self._r.set(spec_key, run_id, nx=True):
            existing = self._r.get(spec_key)
            row = self._r.hgetall(JOB_PREFIX + existing) if existing else {}
            if row:
                status = AnalysisStatus(row["status"])
                if status is AnalysisStatus.SUCCEEDED:
                    return Submission(run_id=row["run_id"], status=status, from_cache=True)
                if not status.is_terminal:
                    return Submission(run_id=row["run_id"], status=status, deduplicated=True)
            self._r.set(spec_key, run_id)  # stale key for a failed/cancelled/missing run
        now = self._clock().isoformat()
        self._r.hset(
            JOB_PREFIX + run_id,
            mapping={
                "run_id": run_id,
                "case_id": case.case_id,
                "project_id": project_id or "",
                "requested_by": requested_by or "",
                "spec_hash": request.spec_hash,
                "status": _QUEUED.value,
                "data_mode": request.data_mode,
                "is_simulated": json.dumps(request.is_simulated),
                "attempts": "0",
                "max_attempts": str(self._max_attempts),
                "cancel_requested": "0",
                "request": request.model_dump_json(),
                "stage_log": "{}",
                "created_at": now,
                "updated_at": now,
            },
        )
        self._enqueue(run_id)
        return Submission(run_id=run_id, status=_QUEUED)

    def cancel(self, run_id: str) -> AnalysisStatus:
        """Cancel a queued job at once; flag a running one (it stops at a checkpoint)."""
        row = self._row(run_id)
        status = AnalysisStatus(row["status"])
        if status is AnalysisStatus.CANCELLED:
            return status
        if status.is_terminal:
            raise IllegalTransitionError(run_id, status, AnalysisStatus.CANCELLED)
        update = {"cancel_requested": "1", "updated_at": self._clock().isoformat()}
        if status is _QUEUED:
            update["status"] = AnalysisStatus.CANCELLED.value
            self._r.delete(SPEC_PREFIX + row["spec_hash"])
        self._r.hset(JOB_PREFIX + run_id, mapping=update)
        return AnalysisStatus(update.get("status", status.value))

    def status(self, run_id: str) -> JobStatus | None:
        """The job's state, or ``None`` if there is no such run."""
        row = self._r.hgetall(JOB_PREFIX + run_id)
        if not row:
            return None
        result = AnalysisResult.model_validate_json(row["result"]) if row.get("result") else None
        stage_log = {k: datetime.fromisoformat(v) for k, v in json.loads(row["stage_log"]).items()}
        return JobStatus(
            run_id=run_id,
            case_id=row["case_id"],
            project_id=row.get("project_id") or None,
            status=AnalysisStatus(row["status"]),
            engine_status=result.status.value if result is not None else None,
            data_mode=row["data_mode"],
            is_simulated=json.loads(row["is_simulated"]),
            attempts=int(row["attempts"]),
            max_attempts=int(row["max_attempts"]),
            available_at=None,
            lease_expires_at=None,
            locked_by=row.get("locked_by"),
            cancel_requested=row["cancel_requested"] == "1",
            last_error=json.loads(row["last_error"]) if row.get("last_error") else None,
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=_opt_dt(row.get("updated_at")),
            heartbeat_at=_opt_dt(row.get("heartbeat_at")),
            stage=row.get("stage") or None,
            stage_log=stage_log,
            metrics=result.metrics if result is not None else None,
            error=result.error if result is not None else None,
            failure_reason=row.get("failure_reason"),
            as_of=self._clock(),
        )

    # -- worker side ------------------------------------------------------------------

    def _row(self, run_id: str) -> dict[str, str]:
        row = self._r.hgetall(JOB_PREFIX + run_id)
        if not row:
            raise JobNotFoundError(f"no run {run_id!r}")
        return row

    def load_request(self, run_id: str) -> AnalysisRequest:
        """The request stored at submit time."""
        return AnalysisRequest.model_validate_json(self._row(run_id)["request"])

    def begin(self, run_id: str, worker_id: str) -> bool:
        """Move ``queued -> running`` (stage ``claim``). ``False`` if it is not queued."""
        row = self._row(run_id)
        if row["status"] != _QUEUED.value:
            return False
        now = self._clock().isoformat()
        log = json.loads(row["stage_log"])
        log["claim"] = now
        self._r.hset(
            JOB_PREFIX + run_id,
            mapping={
                "status": _RUNNING.value,
                "locked_by": worker_id,
                "attempts": str(int(row["attempts"]) + 1),
                "stage": "claim",
                "stage_log": json.dumps(log),
                "heartbeat_at": now,
                "updated_at": now,
            },
        )
        return True

    def checkpoint(self, run_id: str, stage: str) -> None:
        """Record that ``stage`` begins; stop if cancellation was requested.

        Raises:
            JobCancelledError: after marking the run ``cancelled``.
        """
        if stage not in LIVE_STAGES:
            raise ValueError(f"unknown stage {stage!r}; expected one of {LIVE_STAGES}")
        row = self._row(run_id)
        now = self._clock().isoformat()
        if row["cancel_requested"] == "1":
            self._finish(run_id, row, AnalysisStatus.CANCELLED)
            raise JobCancelledError(run_id)
        log = json.loads(row["stage_log"])
        log[stage] = now
        self._r.hset(
            JOB_PREFIX + run_id,
            mapping={
                "stage": stage,
                "stage_log": json.dumps(log),
                "heartbeat_at": now,
                "updated_at": now,
            },
        )

    def complete(self, run_id: str, result: AnalysisResult) -> AnalysisStatus:
        """Store the result. A refusal is ``SUCCEEDED``: it is a scientific outcome."""
        result = result.model_copy(update={"run_id": run_id})
        row = self._row(run_id)
        self._finish(run_id, row, AnalysisStatus.SUCCEEDED, {"result": result.model_dump_json()})
        return AnalysisStatus.SUCCEEDED

    def fail(self, run_id: str, reason: str, *, retryable: bool) -> AnalysisStatus:
        """Fail the job, or put it back to ``queued`` if retryable and attempts remain."""
        row = self._row(run_id)
        error = json.dumps({"message": reason})
        if retryable and int(row["attempts"]) < int(row["max_attempts"]):
            self._r.hset(
                JOB_PREFIX + run_id,
                mapping={
                    "status": _QUEUED.value,
                    "last_error": error,
                    "stage": "",
                    "updated_at": self._clock().isoformat(),
                },
            )
            self._enqueue(run_id)
            return _QUEUED
        self._finish(
            run_id, row, AnalysisStatus.FAILED, {"failure_reason": reason, "last_error": error}
        )
        return AnalysisStatus.FAILED

    def _finish(
        self,
        run_id: str,
        row: dict[str, str],
        status: AnalysisStatus,
        extra: Mapping[str, str] | None = None,
    ) -> None:
        mapping = {"status": status.value, "updated_at": self._clock().isoformat(), **(extra or {})}
        self._r.hset(JOB_PREFIX + run_id, mapping=mapping)
        if status is not AnalysisStatus.SUCCEEDED:
            self._r.delete(SPEC_PREFIX + row["spec_hash"])


def process_job(
    queue: RedisJobQueue,
    run_id: str,
    worker_id: str,
    resolve_access: ResolveAccess,
    *,
    run: RunEngine = run_analysis,
) -> AnalysisStatus | None:
    """Run one job through ``data -> engine -> record``. ``None`` if it was not queued."""
    if not queue.begin(run_id, worker_id):
        return None
    request = queue.load_request(run_id)
    try:
        queue.checkpoint(run_id, "data")
        try:
            data = resolve_access(request)
        except DataUnavailableError as exc:
            return queue.fail(run_id, f"data unavailable: {exc}", retryable=True)
        queue.checkpoint(run_id, "engine")
        result = run(request, data)
        queue.checkpoint(run_id, "record")
        return queue.complete(run_id, result)
    except JobCancelledError:
        return AnalysisStatus.CANCELLED
    except Exception as exc:
        queue.fail(run_id, f"{type(exc).__name__}: {exc}", retryable=False)
        raise


async def run_job(ctx: dict[str, Any], run_id: str) -> str | None:
    """The arq task. ``ctx`` holds ``queue`` and ``resolve_access``; optional ``run``."""
    status = await asyncio.to_thread(
        process_job,
        ctx["queue"],
        run_id,
        ctx.get("worker_id", "arq"),
        ctx["resolve_access"],
        run=ctx.get("run", run_analysis),
    )
    return status.value if status is not None else None


def worker_settings(url: str, resolve_access: ResolveAccess, **overrides: Any) -> type:
    """Build an arq ``WorkerSettings`` class, for ``arq your_module.WorkerSettings``.

    Example::

        WorkerSettings = worker_settings(redis_url_from_env() or "", my_resolve_access)
    """
    queue = RedisJobQueue.from_url(url)

    async def startup(ctx: dict[str, Any]) -> None:
        ctx["queue"] = queue
        ctx["resolve_access"] = resolve_access

    attrs: dict[str, Any] = {
        "functions": [run_job],
        "on_startup": startup,
        "redis_settings": _require("arq.connections").RedisSettings.from_dsn(url),
        **overrides,
    }
    return type("WorkerSettings", (), attrs)


def select_job_control(sql_factory: Callable[[], Any]) -> Any:
    """A :class:`RedisJobQueue` when ``REDIS_URL`` is set, else ``sql_factory()`` unchanged."""
    url = redis_url_from_env()
    return RedisJobQueue.from_url(url) if url else sql_factory()
