"""Retry and rate limiting for calls to an external data provider.

**Owner: Bhumi.**

Two layers retry an outage, deliberately at different scales:

* **here, per call:** a few attempts over about fifteen seconds, for blips (a
  dropped connection, a 429, a 503);
* **the job layer (#24):** whole attempts 30 s, then 60 s apart, for outages of
  minutes. It sees only what this layer gives up on.

So the worst case for a persistent outage is bounded (attempts here x attempts
there), and neither layer hides a permanent failure: an error classified as
permanent is raised at once, without a second try.

Waits are fixed, not jittered, so a retry schedule reads the same in tests and
in logs (as :func:`groundtruth.platform.jobs.lifecycle.backoff_delay`).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

T = TypeVar("T")


class TransientError(Exception):
    """A failure worth another attempt. Carries an already-redacted reason."""


class PermanentError(Exception):
    """A failure that another attempt would repeat. Carries an already-redacted reason."""


@dataclass(frozen=True)
class RetryPolicy:
    """How many times to try a call, and how long to wait between tries."""

    max_attempts: int = 4
    delays_s: tuple[float, ...] = (2.0, 4.0, 8.0)

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")

    def delay(self, failed_attempt: int) -> float:
        """Wait after failed attempt ``failed_attempt`` (1-based); the last delay repeats."""
        if not self.delays_s:
            return 0.0
        return self.delays_s[min(failed_attempt, len(self.delays_s)) - 1]


def call_with_retry(
    call: Callable[[], T],
    *,
    policy: RetryPolicy,
    sleep: Callable[[float], None] = time.sleep,
    on_retry: Callable[[int, float, TransientError], None] | None = None,
) -> T:
    """Run ``call``, retrying :class:`TransientError` up to the policy's limit.

    Raises:
        TransientError: the last one, once attempts are exhausted.
        PermanentError: at once, on the first one.
    """
    attempt = 1
    while True:
        try:
            return call()
        except TransientError as exc:
            if attempt >= policy.max_attempts:
                raise
            wait = policy.delay(attempt)
            if on_retry is not None:
                on_retry(attempt, wait, exc)
            sleep(wait)
            attempt += 1


class RateLimiter:
    """At most ``per_minute`` calls a minute, spaced evenly, across threads.

    Spacing rather than bursting keeps a worker under Earth Engine's request-rate
    limit without needing to know it exactly; a 429 that still gets through is a
    :class:`TransientError` and is retried.
    """

    def __init__(
        self,
        per_minute: int,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if per_minute < 1:
            raise ValueError("per_minute must be at least 1")
        self.interval_s = 60.0 / per_minute
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._next_at: float | None = None

    def acquire(self) -> float:
        """Block until a call may start. Returns how long it waited."""
        with self._lock:
            now = self._clock()
            start = now if self._next_at is None else max(now, self._next_at)
            self._next_at = start + self.interval_s
        wait = start - now
        if wait > 0:
            self._sleep(wait)
        return wait


_shared_limiters: dict[int, RateLimiter] = {}
_shared_lock = threading.Lock()


def shared_rate_limiter(per_minute: int) -> RateLimiter:
    """The process-wide limiter for a rate, so every client in a process shares one budget."""
    with _shared_lock:
        limiter = _shared_limiters.get(per_minute)
        if limiter is None:
            limiter = _shared_limiters[per_minute] = RateLimiter(per_minute)
        return limiter


__all__ = [
    "PermanentError",
    "RateLimiter",
    "RetryPolicy",
    "TransientError",
    "call_with_retry",
    "shared_rate_limiter",
]
