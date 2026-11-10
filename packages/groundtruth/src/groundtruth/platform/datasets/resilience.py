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

A third piece keeps a long outage from turning into a retry storm (#48): a
:class:`CircuitBreaker` per provider. After five calls in a row fail (each after its
retries), calls fail at once for a minute without touching the provider, then one
trial call decides whether it is back.

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


class CircuitOpenError(Exception):
    """A call refused at once because its provider is known to be down (#48).

    Callers turn it into their own "unavailable" error, exactly as they do for a provider that
    failed after its retries: an Earth Engine call into ``DataUnavailableError`` (so a job reports
    ``data_unavailable``, never a fixture), a narration into ``narration_failed``.
    """

    def __init__(self, provider: str, retry_after_s: float) -> None:
        self.provider = provider
        self.retry_after_s = retry_after_s
        super().__init__(
            f"{provider} is unavailable (circuit open after repeated failures); "
            f"not calling it again for {retry_after_s:.0f} s"
        )


class CircuitBreaker:
    """Stop calling a provider that keeps failing, so an outage cannot become a retry storm.

    **Closed** (normal): calls go through. ``failure_threshold`` calls in a row that fail (each
    after its own retries) open the circuit. **Open**: every call fails at once with
    :class:`CircuitOpenError`, without touching the provider, for ``cooldown_s``. **Half-open**:
    after the cool-down, one trial call goes through; success closes the circuit, failure opens
    it again for another cool-down.

    Only outages count. A :class:`PermanentError` (bad credentials, a malformed request) says
    nothing about whether the provider is up, so it passes through without counting. Process
    local, like :class:`RateLimiter`: each worker or API process judges for itself.
    """

    def __init__(
        self,
        provider: str,
        *,
        failure_threshold: int = 5,
        cooldown_s: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
        on_open: Callable[[str], None] | None = None,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be at least 1")
        if cooldown_s <= 0:
            raise ValueError("cooldown_s must be positive")
        self.provider = provider
        self.failure_threshold = failure_threshold
        self.cooldown_s = cooldown_s
        self._clock = clock
        self._on_open = on_open
        self._lock = threading.Lock()
        self._failures = 0
        self._opened_at: float | None = None
        self._trial_in_flight = False

    @property
    def state(self) -> str:
        """``closed``, ``open`` or ``half_open``."""
        with self._lock:
            return self._state_locked()

    def _state_locked(self) -> str:
        if self._opened_at is None:
            return "closed"
        if self._clock() - self._opened_at >= self.cooldown_s:
            return "half_open"
        return "open"

    def _admit(self) -> None:
        with self._lock:
            state = self._state_locked()
            if state == "closed":
                return
            if state == "half_open" and not self._trial_in_flight:
                self._trial_in_flight = True  # exactly one trial call
                return
            assert self._opened_at is not None
            remaining = max(0.0, self.cooldown_s - (self._clock() - self._opened_at))
            raise CircuitOpenError(self.provider, remaining or self.cooldown_s)

    def _record(self, *, success: bool) -> None:
        opened = False
        with self._lock:
            was_trial = self._trial_in_flight
            self._trial_in_flight = False
            if success:
                self._failures = 0
                self._opened_at = None
                return
            self._failures += 1
            if was_trial or self._failures >= self.failure_threshold:
                self._opened_at = self._clock()
                opened = True
        if opened and self._on_open is not None:
            self._on_open(self.provider)

    def call(
        self, call: Callable[[], T], *, counts: Callable[[Exception], bool] | None = None
    ) -> T:
        """Run ``call`` through the breaker.

        Args:
            call: The provider call, with its own retries already inside it.
            counts: Whether an exception is an outage that counts against the provider.
                Default: anything but a :class:`PermanentError`.

        Raises:
            CircuitOpenError: the circuit is open; the provider was not called.
        """
        self._admit()
        try:
            result = call()
        except Exception as exc:
            outage = counts(exc) if counts is not None else not isinstance(exc, PermanentError)
            if outage:
                self._record(success=False)
            else:
                with self._lock:
                    self._trial_in_flight = False  # not an outage: neither opens nor closes
            raise
        self._record(success=True)
        return result


BREAKER_PROVIDERS: tuple[str, ...] = ("earth_engine", "gemini", "anthropic")
"""Providers with a shared breaker; also the only values of the ``provider`` metric label."""

_shared_breakers: dict[str, CircuitBreaker] = {}
_breaker_lock = threading.Lock()


def shared_breaker(provider: str) -> CircuitBreaker:
    """The process-wide breaker for ``provider``: 5 failures in a row, 60 s cool-down (#48)."""
    with _breaker_lock:
        breaker = _shared_breakers.get(provider)
        if breaker is None:
            from groundtruth.platform.metrics import record_circuit_open

            breaker = _shared_breakers[provider] = CircuitBreaker(
                provider, on_open=record_circuit_open
            )
        return breaker


def reset_breakers() -> None:
    """Forget every breaker's state. For tests."""
    with _breaker_lock:
        _shared_breakers.clear()


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
    "BREAKER_PROVIDERS",
    "CircuitBreaker",
    "CircuitOpenError",
    "PermanentError",
    "RateLimiter",
    "RetryPolicy",
    "TransientError",
    "call_with_retry",
    "reset_breakers",
    "shared_breaker",
    "shared_rate_limiter",
]
