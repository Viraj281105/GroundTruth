"""Prometheus metrics for the API and the worker (#50).

**Owner: Bhumi.** Four questions an operator must be able to answer, one metric family each:

=================================  ===========================================================
How long does each stage take?     ``gt_stage_duration_seconds{stage}``
How much work is waiting?          ``gt_queue_jobs{state}``, ``gt_queue_oldest_queued_seconds``
How often does the engine refuse?  ``gt_runs_finished_total{outcome, path}``
Is the cache doing its job?        ``gt_cache_requests_total{cache, result}``
=================================  ===========================================================

The refusal rate is the one to watch (``docs/operations/README.md``): a sudden change means the
data or the method changed, and a rate of zero is more suspicious than a high one. It is
computed in PromQL from ``gt_runs_finished_total``; a refusal is never counted as a failure.

**Labels come from fixed lists only** (:data:`STAGES`, :data:`OUTCOMES`, :data:`PATHS`,
:data:`CACHES`, :data:`CACHE_RESULTS`, :data:`QUEUE_STATES`). No case id, run id, user, email or
organization is ever a label: they would leak tenant data to anyone who can read the metrics,
and every distinct value is a new time series. A value outside the list is recorded as
``other`` rather than trusted.

Each process serves its metrics on an internal port (:func:`start_metrics_server`): the API on
``API_METRICS_PORT`` (9464), a worker on ``WORKER_METRICS_PORT`` (9465). Neither is the public
API port, and neither is published outside the deployment's own network.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from prometheus_client import (
    CollectorRegistry,
    Counter,
    GCCollector,
    Histogram,
    PlatformCollector,
    ProcessCollector,
    start_http_server,
)
from prometheus_client.core import GaugeMetricFamily
from prometheus_client.registry import Collector

from groundtruth.logging import get_logger

logger = get_logger("metrics")

STAGES = ("data", "engine", "record")
"""The job stages a worker times (``platform/jobs/runner.py``)."""
OUTCOMES = ("completed", "refused", "errored", "failed", "retried", "cancelled")
"""How a run ended. ``refused`` is a scientific outcome; ``errored`` (the engine could not run)
and ``failed`` (the job could not finish) are malfunctions; ``retried`` went back to the queue."""
MALFUNCTIONS = ("errored", "failed")
PATHS = ("job", "verify")
"""``job``: a queued run a worker processed. ``verify``: the synchronous ``/verify`` route."""
CACHES = ("result", "reduction")
"""``result``: a submitted run answered from a stored result. ``reduction``: one Earth Engine
reduction answered from the reduction cache."""
CACHE_RESULTS = ("hit", "miss")
QUEUE_STATES = ("queued", "running")
PROVIDERS = ("earth_engine", "gemini", "anthropic")
"""External providers with a circuit breaker (#48)."""
OTHER = "other"

LABEL_VALUES: dict[str, tuple[str, ...]] = {
    "stage": STAGES,
    "outcome": OUTCOMES,
    "path": PATHS,
    "cache": CACHES,
    "result": CACHE_RESULTS,
    "state": QUEUE_STATES,
    "provider": PROVIDERS,
}
"""Every label any GroundTruth metric may carry, and every value it may take."""

REGISTRY = CollectorRegistry(auto_describe=True)
ProcessCollector(registry=REGISTRY)
PlatformCollector(registry=REGISTRY)
GCCollector(registry=REGISTRY)

STAGE_DURATION = Histogram(
    "gt_stage_duration_seconds",
    "Wall time of one job stage.",
    ["stage"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300, 600, 1800),
    registry=REGISTRY,
)
RUNS_FINISHED = Counter(
    "gt_runs_finished",
    "Runs that ended, by outcome. The refusal rate is refused / (completed + refused).",
    ["outcome", "path"],
    registry=REGISTRY,
)
CACHE_REQUESTS = Counter(
    "gt_cache_requests",
    "Cache lookups, by cache and result.",
    ["cache", "result"],
    registry=REGISTRY,
)
SUBMISSIONS_RATE_LIMITED = Counter(
    "gt_submissions_rate_limited",
    "Analysis submissions refused because the caller was over the limit (#51).",
    ["path"],
    registry=REGISTRY,
)

CIRCUIT_OPENED = Counter(
    "gt_circuit_open",
    "Times a provider's circuit breaker opened: it kept failing, so calls fail fast (#48).",
    ["provider"],
    registry=REGISTRY,
)

# Every series exists at zero from the start, so "no refusals in 24 hours" is a fact the
# alert can see rather than a missing series.
for _outcome in (*OUTCOMES, OTHER):
    for _path in PATHS:
        RUNS_FINISHED.labels(outcome=_outcome, path=_path)
for _cache in CACHES:
    for _result in CACHE_RESULTS:
        CACHE_REQUESTS.labels(cache=_cache, result=_result)
for _path in PATHS:
    SUBMISSIONS_RATE_LIMITED.labels(path=_path)
for _provider in PROVIDERS:
    CIRCUIT_OPENED.labels(provider=_provider)


def _allowed(label: str, value: str) -> str:
    return value if value in LABEL_VALUES[label] else OTHER


@contextmanager
def stage_timer(stage: str) -> Iterator[None]:
    """Time the block as ``stage``, whether it returns or raises."""
    started = time.perf_counter()
    try:
        yield
    finally:
        STAGE_DURATION.labels(stage=_allowed("stage", stage)).observe(time.perf_counter() - started)


def record_outcome(outcome: str, *, path: str = "job") -> None:
    """Count one finished run."""
    RUNS_FINISHED.labels(outcome=_allowed("outcome", outcome), path=_allowed("path", path)).inc()


def outcome_of_engine_status(engine_status: str) -> str:
    """The outcome label for what the engine returned: completed, refused, or errored."""
    return {"completed": "completed", "refused": "refused", "error": "errored"}.get(
        engine_status, OTHER
    )


def record_cache(cache: str, *, hit: bool) -> None:
    """Count one cache lookup."""
    CACHE_REQUESTS.labels(cache=_allowed("cache", cache), result="hit" if hit else "miss").inc()


def record_circuit_open(provider: str) -> None:
    """Count one opening of a provider's circuit breaker."""
    CIRCUIT_OPENED.labels(provider=_allowed("provider", provider)).inc()
    logger.warning("circuit opened for %s: it keeps failing; calls fail fast for a while", provider)


def record_rate_limited(path: str) -> None:
    SUBMISSIONS_RATE_LIMITED.labels(path=_allowed("path", path)).inc()


class QueueCollector(Collector):
    """Queue depth, read from the database when Prometheus scrapes.

    The database is the one place that knows what is waiting across every API process and
    worker, so the depth is read, not counted. Registered by the API only, so the depth is
    reported once. ``gt_queue_metrics_up`` is 0 when the read failed, so a broken read shows up
    as an alert instead of a reassuring zero.
    """

    def __init__(self, read: Callable[[], tuple[dict[str, int], float | None]]) -> None:
        self._read = read

    def describe(self) -> Iterable[Any]:
        return []

    def collect(self) -> Iterable[Any]:
        up = GaugeMetricFamily("gt_queue_metrics_up", "1 if the queue depth could be read.")
        try:
            counts, oldest = self._read()
        except Exception as exc:  # a scrape must not crash the endpoint
            logger.warning("could not read the queue depth: %s", type(exc).__name__)
            up.add_metric([], 0)
            yield up
            return
        up.add_metric([], 1)
        yield up
        jobs = GaugeMetricFamily("gt_queue_jobs", "Runs waiting or in progress.", labels=["state"])
        for state in QUEUE_STATES:
            jobs.add_metric([state], counts.get(state, 0))
        yield jobs
        yield GaugeMetricFamily(
            "gt_queue_oldest_queued_seconds",
            "Age of the oldest queued run; 0 when nothing is queued.",
            value=oldest or 0.0,
        )


def database_queue_reader(sessions: Any) -> Callable[[], tuple[dict[str, int], float | None]]:
    """A reader for :class:`QueueCollector` over the ``analysis_runs`` table."""
    import sqlalchemy as sa

    from groundtruth.platform.store.models import AnalysisRunRow

    def read() -> tuple[dict[str, int], float | None]:
        with sessions() as db:
            rows = db.execute(
                sa.select(AnalysisRunRow.status, sa.func.count())
                .where(AnalysisRunRow.status.in_(QUEUE_STATES))
                .group_by(AnalysisRunRow.status)
            ).all()
            oldest = db.execute(
                sa.select(sa.func.min(AnalysisRunRow.created_at)).where(
                    AnalysisRunRow.status == "queued"
                )
            ).scalar_one_or_none()
        counts = {str(status): int(count) for status, count in rows}
        if oldest is None:
            return counts, None
        if oldest.tzinfo is None:
            oldest = oldest.replace(tzinfo=UTC)
        return counts, max(0.0, (datetime.now(UTC) - oldest).total_seconds())

    return read


_queue_collector: QueueCollector | None = None


def register_queue_collector(sessions: Any) -> None:
    """Report the queue depth from this process. Call once, from the API."""
    global _queue_collector
    if _queue_collector is not None:
        REGISTRY.unregister(_queue_collector)
    _queue_collector = QueueCollector(database_queue_reader(sessions))
    REGISTRY.register(_queue_collector)


def unregister_queue_collector() -> None:
    """Stop reporting the queue depth from this process. For tests."""
    global _queue_collector
    if _queue_collector is not None:
        REGISTRY.unregister(_queue_collector)
        _queue_collector = None


def start_metrics_server(port: int, address: str) -> bool:
    """Serve ``/metrics`` on ``address:port`` in a background thread. False if it could not.

    ``port`` 0 turns metrics off. A port already in use (two workers on one machine) is logged
    and the process carries on without metrics: monitoring must never stop the work.
    """
    if port <= 0:
        logger.info("metrics disabled (port 0)")
        return False
    try:
        start_http_server(port, addr=address, registry=REGISTRY)
    except OSError as exc:
        logger.warning("metrics not served: %s:%d is unavailable (%s)", address, port, exc)
        return False
    logger.info("metrics served on %s:%d/metrics", address, port)
    return True


__all__ = [
    "CACHES",
    "LABEL_VALUES",
    "OUTCOMES",
    "PATHS",
    "REGISTRY",
    "STAGES",
    "QueueCollector",
    "database_queue_reader",
    "outcome_of_engine_status",
    "record_cache",
    "record_outcome",
    "record_rate_limited",
    "register_queue_collector",
    "stage_timer",
    "start_metrics_server",
    "unregister_queue_collector",
]
