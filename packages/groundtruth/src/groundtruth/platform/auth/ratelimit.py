"""In-memory sliding-window limiter for failed sign-ins.

Per process: with several API workers each keeps its own counts, so the effective limit
is multiplied by the worker count. Documented in ``docs/security/auth.md``.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable

MAX_FAILURES = 5
WINDOW_SECONDS = 15 * 60
_MAX_KEYS = 10_000


class FailureLimiter:
    def __init__(
        self,
        max_failures: int = MAX_FAILURES,
        window: float = WINDOW_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max = max_failures
        self._window = window
        self._clock = clock
        self._failures: dict[tuple[str, str], deque[float]] = {}
        self._lock = threading.Lock()

    def _prune(self, key: tuple[str, str], now: float) -> deque[float]:
        events = self._failures.get(key)
        if events is None:
            return deque()
        while events and now - events[0] >= self._window:
            events.popleft()
        if not events:
            del self._failures[key]
            return deque()
        return events

    def retry_after(self, key: tuple[str, str]) -> int | None:
        """Seconds until another attempt is allowed, or ``None`` when one is allowed now."""
        with self._lock:
            now = self._clock()
            events = self._prune(key, now)
            if len(events) < self._max:
                return None
            return max(1, int(self._window - (now - events[0])) + 1)

    def record_failure(self, key: tuple[str, str]) -> None:
        with self._lock:
            now = self._clock()
            if key not in self._failures and len(self._failures) >= _MAX_KEYS:
                # Bound memory: drop the oldest-inserted key.
                self._failures.pop(next(iter(self._failures)))
            events = self._prune(key, now)
            events.append(now)
            self._failures[key] = events

    def reset(self, key: tuple[str, str]) -> None:
        with self._lock:
            self._failures.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._failures.clear()


login_limiter = FailureLimiter()
