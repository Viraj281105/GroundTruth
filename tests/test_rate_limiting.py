"""Tests for API Rate Limiting, Window Expiry Recovery, and Client Isolation.

Verifies:
- MemoryRateLimitBackend sliding window enforcement.
- HTTP 429 status code and standard headers (Retry-After, X-RateLimit-Limit, X-RateLimit-Remaining).
- Recovery when window expires.
- Client isolation (IP and session separation).
- RateLimiter dependency on FastAPI routes.
"""

from __future__ import annotations

import time

import pytest
from fastapi import Depends, FastAPI, status
from fastapi.testclient import TestClient

from groundtruth.platform.api.rate_limiting import (
    MemoryRateLimitBackend,
    RateLimiter,
)
from groundtruth.platform.config import get_settings


@pytest.fixture(autouse=True)
def _enable_rate_limiting(monkeypatch):
    monkeypatch.setattr(get_settings(), "rate_limit_enabled", True)


def test_sliding_window_enforcement_and_headers() -> None:
    backend = MemoryRateLimitBackend()
    limiter = RateLimiter(limit=3, window_seconds=2, scope_prefix="test", backend=backend)

    app = FastAPI()

    @app.get("/test-endpoint", dependencies=[Depends(limiter)])
    def route():
        return {"status": "ok"}

    client = TestClient(app)

    # Hits 1, 2, 3 should succeed
    r1 = client.get("/test-endpoint")
    assert r1.status_code == status.HTTP_200_OK
    assert r1.headers["X-RateLimit-Limit"] == "3"
    assert r1.headers["X-RateLimit-Remaining"] == "2"

    r2 = client.get("/test-endpoint")
    assert r2.status_code == status.HTTP_200_OK
    assert r2.headers["X-RateLimit-Remaining"] == "1"

    r3 = client.get("/test-endpoint")
    assert r3.status_code == status.HTTP_200_OK
    assert r3.headers["X-RateLimit-Remaining"] == "0"

    # Hit 4 must be rejected with 429
    r4 = client.get("/test-endpoint")
    assert r4.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert "Rate limit exceeded" in r4.json()["detail"]
    assert "Retry-After" in r4.headers
    assert int(r4.headers["Retry-After"]) >= 1


def test_rate_limit_recovery_after_expiry() -> None:
    backend = MemoryRateLimitBackend()
    # 2 requests per 1 second
    limiter = RateLimiter(limit=2, window_seconds=1, scope_prefix="recover", backend=backend)

    app = FastAPI()

    @app.get("/fast-window", dependencies=[Depends(limiter)])
    def route():
        return {"status": "ok"}

    client = TestClient(app)

    assert client.get("/fast-window").status_code == 200
    assert client.get("/fast-window").status_code == 200
    assert client.get("/fast-window").status_code == 429

    # Wait for sliding window to elapse
    time.sleep(1.1)

    # Must recover and succeed again
    r_recovered = client.get("/fast-window")
    assert r_recovered.status_code == 200
    assert r_recovered.headers["X-RateLimit-Remaining"] == "1"


def test_client_isolation_different_ips(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = MemoryRateLimitBackend()
    limiter = RateLimiter(limit=2, window_seconds=10, scope_prefix="isolate", backend=backend)

    app = FastAPI()

    @app.get("/isolated", dependencies=[Depends(limiter)])
    def route():
        return {"status": "ok"}

    client = TestClient(app)

    # By default (trust_proxy_headers=False), spoofed X-Forwarded-For is ignored.
    headers_a = {"X-Forwarded-For": "198.51.100.1"}
    headers_b = {"X-Forwarded-For": "203.0.113.42"}
    assert client.get("/isolated", headers=headers_a).status_code == 200
    assert client.get("/isolated", headers=headers_b).status_code == 200
    assert client.get("/isolated", headers=headers_b).status_code == 429

    # When behind a configured reverse proxy (trust_proxy_headers=True), client IPs isolate cleanly.
    backend.clear()
    monkeypatch.setattr(get_settings(), "trust_proxy_headers", True)
    assert client.get("/isolated", headers=headers_a).status_code == 200
    assert client.get("/isolated", headers=headers_a).status_code == 200
    assert client.get("/isolated", headers=headers_a).status_code == 429

    # Client B on a different IP must not be blocked
    r_b = client.get("/isolated", headers=headers_b)
    assert r_b.status_code == 200
    assert r_b.headers["X-RateLimit-Remaining"] == "1"


def test_memory_rate_limit_backend_bounded_keys() -> None:
    backend = MemoryRateLimitBackend(max_keys=3)
    for i in range(10):
        allowed, _, _ = backend.hit(f"k{i}", limit=2, window_seconds=60)
        assert allowed is True
    assert len(backend._hits) <= 3
