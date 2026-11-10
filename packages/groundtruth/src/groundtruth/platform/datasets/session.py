"""One Earth Engine session: sign-in, rate limiting, retries and redaction.

**Owner: Bhumi.**

Every service that talks to Earth Engine (observations #22, covariates and unit
construction #23) goes through this class, so each rule below holds in one place:

* sign in once, on first use, never at construction;
* every call counts against the same rate limit;
* transient errors are retried here, for seconds; the job layer (#24) retries whole
  attempts for minutes (:mod:`~groundtruth.platform.datasets.resilience`);
* external error text is redacted against the key before it reaches a message or a
  log, and every translated exception is raised ``from None``;
* missing or rejected credentials are a :class:`ConfigurationError`; every data
  failure is a :class:`DataUnavailableError`. Nothing falls back to fixtures.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Protocol, TypeVar

from pydantic import SecretStr

from groundtruth.contracts.errors import ConfigurationError, DataUnavailableError
from groundtruth.logging import get_logger
from groundtruth.platform.datasets.earthengine import (
    ServiceAccountKey,
    classify,
    load_service_account_key,
)
from groundtruth.platform.datasets.resilience import (
    PermanentError,
    RateLimiter,
    RetryPolicy,
    TransientError,
    call_with_retry,
)

logger = get_logger("datasets.earthengine")

T = TypeVar("T")


class SignInBackend(Protocol):
    """The one thing a session needs from an Earth Engine backend."""

    def initialize(self, key: ServiceAccountKey, project: str) -> None:
        """Authenticate this process."""
        ...


class EarthEngineSession:
    """Signed-in, rate-limited, retried access to one Earth Engine backend.

    Args:
        credentials: ``GEE_SERVICE_ACCOUNT_JSON``: a key file path or the key JSON.
        project: The Google Cloud project; defaults to the key's ``project_id``.
        backend: The Earth Engine client to sign in.
        rate_limiter: Shared request budget; ``None`` means unlimited.
        retry_policy: Per-call retries for transient failures.
    """

    def __init__(
        self,
        *,
        credentials: SecretStr | None,
        project: str | None,
        backend: SignInBackend,
        rate_limiter: RateLimiter | None = None,
        retry_policy: RetryPolicy | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._credentials = credentials
        self._project = project.strip() if project and project.strip() else None
        self._backend = backend
        self._limiter = rate_limiter
        self._retry = retry_policy or RetryPolicy()
        self._sleep = sleep
        self._key: ServiceAccountKey | None = None
        self._init_lock = threading.Lock()

    def ensure_initialized(self) -> None:
        """Sign in once, on first use. Never before."""
        if self._key is not None:
            return
        with self._init_lock:
            if self._key is not None:
                return
            key = load_service_account_key(self._credentials)
            project = self._project or key.project_id
            if not project:
                raise ConfigurationError(
                    "GOOGLE_CLOUD_PROJECT is not set and the service-account key names no "
                    "project_id; Earth Engine needs a Cloud project"
                )
            try:
                self._attempt(key, lambda: self._backend.initialize(key, project))
            except TransientError as exc:
                raise DataUnavailableError(
                    f"could not reach Earth Engine to sign in after {self._retry.max_attempts} "
                    f"attempts: {exc}"
                ) from None
            except PermanentError as exc:
                raise ConfigurationError(
                    f"Earth Engine rejected the service-account credentials for project "
                    f"{project!r} ({exc}). Check that the key is active and that the account "
                    "is registered for Earth Engine on that project."
                ) from None
            self._key = key
            logger.info("Earth Engine initialised", extra={"project": project})

    def call(self, what: str, call: Callable[[], T]) -> T:
        """One Earth Engine request: signed in, rate-limited, retried, redacted.

        Raises:
            DataUnavailableError: if the call fails for good.
            ConfigurationError: if signing in fails because of the credentials.
        """
        self.ensure_initialized()
        try:
            return self._attempt(self._key, call)
        except TransientError as exc:
            raise DataUnavailableError(
                f"Earth Engine {what} failed after {self._retry.max_attempts} attempts: {exc}"
            ) from None
        except PermanentError as exc:
            raise DataUnavailableError(f"Earth Engine {what} failed: {exc}") from None

    def _attempt(self, key: ServiceAccountKey | None, call: Callable[[], T]) -> T:
        """One rate-limited try, then retries, with every error redacted and classified."""

        def once() -> T:
            if self._limiter is not None:
                self._limiter.acquire()
            try:
                return call()
            except (TransientError, PermanentError):
                raise
            except Exception as exc:
                raise classify(exc, key) from None

        def on_retry(attempt: int, wait: float, exc: TransientError) -> None:
            logger.warning(
                "Earth Engine call failed (transient); retrying",
                extra={"attempt": attempt, "wait_s": wait, "reason": str(exc)},
            )

        return call_with_retry(once, policy=self._retry, sleep=self._sleep, on_retry=on_retry)


__all__ = ["EarthEngineSession", "SignInBackend"]
