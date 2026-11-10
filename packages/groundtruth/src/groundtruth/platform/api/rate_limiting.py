"""Configurable API Rate Limiting for Authentication, Intelligence, and Public Endpoints.

Provides:
- Pluggable storage: thread-safe sliding window MemoryRateLimitBackend for single-node / dev,
  and RedisRateLimitBackend ready for multi-worker production.
- Client key derivation using IP, X-Forwarded-For, and authenticated session tokens.
- Strict HTTP 429 Too Many Requests responses with standard Retry-After and X-RateLimit-* headers.
- Per-route dependency and middleware support.
"""

import hashlib
import logging
import threading
import time
import uuid
from abc import ABC, abstractmethod
from typing import Any

from fastapi import HTTPException, Request, Response, status

from groundtruth.platform.config import get_settings

logger = logging.getLogger(__name__)


class RateLimitBackend(ABC):
    """Abstract backend for recording request hits and enforcing sliding limits."""

    @abstractmethod
    def hit(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int, float]:
        """Record a hit for key.

        Returns:
            (allowed: bool, remaining: int, reset_after_seconds: float)
        """


class MemoryRateLimitBackend(RateLimitBackend):
    """Thread-safe in-memory sliding window rate limiter with bounded key capacity."""

    def __init__(self, max_keys: int = 10_000) -> None:
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()
        self._max_keys = max(1, max_keys)

    def _evict_if_full(self, now: float, window_seconds: int) -> None:
        if len(self._hits) < self._max_keys:
            return
        cutoff = now - window_seconds
        stale = [k for k, ts in self._hits.items() if not ts or max(ts) <= cutoff]
        for k in stale:
            del self._hits[k]
        while len(self._hits) >= self._max_keys:
            oldest_key = min(self._hits, key=lambda k: self._hits[k][-1] if self._hits[k] else 0.0)
            del self._hits[oldest_key]

    def hit(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int, float]:
        now = time.monotonic()
        cutoff = now - window_seconds

        with self._lock:
            # Get existing timestamps and purge expired
            if key not in self._hits:
                self._evict_if_full(now, window_seconds)
            timestamps = self._hits.get(key, [])
            valid_timestamps = [t for t in timestamps if t > cutoff]

            if len(valid_timestamps) >= limit:
                # Limit exceeded; calculate when earliest entry expires
                earliest = valid_timestamps[0]
                reset_after = max(0.1, earliest + window_seconds - now)
                self._hits[key] = valid_timestamps
                return False, 0, reset_after

            # Add current hit
            valid_timestamps.append(now)
            self._hits[key] = valid_timestamps
            remaining = limit - len(valid_timestamps)
            earliest = valid_timestamps[0]
            reset_after = max(0.1, earliest + window_seconds - now)
            return True, remaining, reset_after

    def clear(self) -> None:
        """Reset all in-memory rate-limiting history (used in tests)."""
        with self._lock:
            self._hits.clear()


class RedisRateLimitBackend(RateLimitBackend):
    """Production Redis sorted-set sliding window backend."""

    def __init__(self, redis_client: Any) -> None:
        self._redis = redis_client

    def hit(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int, float]:
        now = time.time()
        cutoff = now - window_seconds
        redis_key = f"gt:ratelimit:{key}"

        try:
            pipe = self._redis.pipeline()
            pipe.zremrangebyscore(redis_key, 0, cutoff)
            pipe.zcard(redis_key)
            pipe.zrange(redis_key, 0, 0, withscores=True)
            pipe.expire(redis_key, window_seconds * 2)
            _, current_count, oldest_items, _ = pipe.execute()

            if current_count >= limit:
                oldest_ts = oldest_items[0][1] if oldest_items else now
                reset_after = max(0.1, oldest_ts + window_seconds - now)
                return False, 0, reset_after

            pipe = self._redis.pipeline()
            pipe.zadd(redis_key, {f"{now}:{uuid.uuid4().hex[:8]}": now})
            pipe.expire(redis_key, window_seconds * 2)
            pipe.execute()

            remaining = limit - (current_count + 1)
            oldest_ts = oldest_items[0][1] if oldest_items else now
            reset_after = max(0.1, oldest_ts + window_seconds - now)
            return True, remaining, reset_after
        except Exception as exc:
            logger.warning("Redis rate limit hit failed, failing open: %s", exc)
            return True, limit - 1, float(window_seconds)


_DEFAULT_BACKEND: RateLimitBackend = MemoryRateLimitBackend()


def get_default_backend() -> RateLimitBackend:
    return _DEFAULT_BACKEND


def get_client_identifier(request: Request, prefix: str = "") -> str:
    """Extract a stable client identifier using direct IP (or XFF if trusted) and session hash."""
    forwarded_for = (
        request.headers.get("x-forwarded-for") if get_settings().trust_proxy_headers else None
    )
    if forwarded_for:
        client_ip = forwarded_for.split(",")[0].strip()
    elif request.client and request.client.host:
        client_ip = request.client.host
    else:
        client_ip = "127.0.0.1"

    # If the user has an active session cookie, include a deterministic SHA-256 prefix
    session_cookie = request.cookies.get("gt_session") or request.headers.get("authorization", "")
    session_part = (
        f":{hashlib.sha256(session_cookie.encode('utf-8')).hexdigest()[:12]}"
        if session_cookie
        else ""
    )

    return f"{prefix}:{client_ip}{session_part}"


class RateLimiter:
    """FastAPI route dependency enforcing rate limits."""

    def __init__(
        self,
        limit: int | None = None,
        window_seconds: int | None = None,
        scope_prefix: str = "rate",
        backend: RateLimitBackend | None = None,
    ) -> None:
        self._limit = limit
        self._window_seconds = window_seconds
        self.scope_prefix = scope_prefix
        self.backend = backend or _DEFAULT_BACKEND

    async def __call__(self, request: Request, response: Response) -> None:
        from groundtruth.platform.config import get_settings

        settings = get_settings()
        if not settings.rate_limit_enabled:
            return

        effective_limit = self._limit or settings.auth_rate_limit
        effective_window = self._window_seconds or settings.rate_limit_window_seconds

        client_key = get_client_identifier(request, prefix=self.scope_prefix)
        allowed, remaining, reset_after = self.backend.hit(
            client_key, effective_limit, effective_window
        )

        # Set standard rate-limit headers on response
        response.headers["X-RateLimit-Limit"] = str(effective_limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, remaining))
        response.headers["X-RateLimit-Reset"] = str(int(reset_after) + 1)

        if not allowed:
            response.headers["Retry-After"] = str(int(reset_after) + 1)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Rate limit exceeded: maximum {effective_limit} requests per "
                    f"{effective_window}s. Retry after {int(reset_after) + 1} seconds."
                ),
                headers={
                    "Retry-After": str(int(reset_after) + 1),
                    "X-RateLimit-Limit": str(effective_limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(reset_after) + 1),
                },
            )
