"""Where the stored-run and job endpoints get their store and job service.

The database is optional: ``groundtruth[api]`` does not install SQLAlchemy (that is the
``db`` extra), and a process may have no ``DATABASE_URL``. ``/health``, ``/cases`` and
``/verify`` never touch the store, and must keep working then. So the store is built
lazily, on first use by a ``/runs`` route, and nothing here imports a database library
at module load.

When the store cannot be built the routes answer 503 with a ``code`` and a hint saying
what to do, never a fallback to a local file: results that quietly went somewhere nobody
else can see would look durable and not be.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from groundtruth.contracts.errors import ConfigurationError
from groundtruth.platform.api.errors import ApiErrorCode, api_error
from groundtruth.platform.jobs.interface import JobControl
from groundtruth.platform.store.interface import (
    EvidenceStore,
    IncompatibleBundleError,
    StoreError,
)


@dataclass(frozen=True)
class _Services:
    """The store and the job service, built together on one database connection."""

    store: EvidenceStore
    jobs: JobControl


_lock = threading.Lock()
_services: _Services | None = None


def _get_services() -> _Services:
    global _services
    if _services is not None:
        return _services
    with _lock:
        if _services is None:
            _services = _build_services()
        return _services


def get_store() -> EvidenceStore:
    """The process's evidence store, built on first use.

    A successful build is kept for the life of the process. A failed one is not: the
    next request tries again, so fixing the configuration needs no restart of the
    request path.

    Raises:
        HTTPException: 503 ``store_not_configured`` or ``store_unavailable``.
    """
    return _get_services().store


def get_jobs() -> JobControl:
    """The process's job service, built on first use alongside the store.

    Raises:
        HTTPException: 503, as for :func:`get_store`.
    """
    return _get_services().jobs


def reset_store() -> None:
    """Forget the cached store and job service. For tests."""
    global _services
    with _lock:
        _services = None


def _build_services() -> _Services:
    try:
        import sqlalchemy as sa

        from groundtruth.platform.jobs.queue import JobQueue
        from groundtruth.platform.jobs.service import SqlJobService
        from groundtruth.platform.store import migrate
        from groundtruth.platform.store.database import (
            create_db_engine,
            create_session_factory,
            resolve_database_url,
        )
        from groundtruth.platform.store.sql import SqlEvidenceStore
    except ImportError as exc:
        raise api_error(
            ApiErrorCode.STORE_NOT_CONFIGURED,
            "Database support is not installed in this environment.",
            hint='Install it with: pip install -e "packages/groundtruth[db]"',
        ) from exc

    try:
        url = resolve_database_url()
    except ConfigurationError as exc:
        raise api_error(
            ApiErrorCode.STORE_NOT_CONFIGURED,
            "No database is configured, so stored runs are not available.",
            hint="Set DATABASE_URL and run the migrations.",
        ) from exc

    try:
        at_head = migrate.is_at_head(url)
    except sa.exc.SQLAlchemyError as exc:
        raise api_error(
            ApiErrorCode.STORE_UNAVAILABLE,
            "The database is configured but could not be reached.",
            hint="Check that it is running and that DATABASE_URL is correct.",
        ) from exc
    if not at_head:
        raise api_error(
            ApiErrorCode.STORE_NOT_CONFIGURED,
            "The database schema is not up to date.",
            hint="Run: python -m apps.worker.main --migrate --exit-when-idle",
        )
    sessions = create_session_factory(create_db_engine(url))
    store = SqlEvidenceStore(sessions)
    from groundtruth.platform.jobs.redis_queue import select_job_control

    # REDIS_URL unset (the default) returns the SQL service unchanged.
    jobs = select_job_control(lambda: SqlJobService(store, JobQueue(sessions)))
    return _Services(store=store, jobs=jobs)


def database_error_types() -> tuple[type[Exception], ...]:
    """Exceptions meaning "the database stopped answering", for the routes to catch.

    Empty when SQLAlchemy is not installed, which also means no store was ever built.
    """
    try:
        import sqlalchemy as sa
    except ImportError:
        return ()
    return (sa.exc.OperationalError, sa.exc.InterfaceError)


@contextmanager
def store_errors() -> Iterator[None]:
    """Turn the store's failures into the API's structured errors."""
    try:
        yield
    except IncompatibleBundleError as exc:
        raise api_error(
            ApiErrorCode.CONTRACT_VERSION_MISMATCH,
            str(exc),
            hint="Migrate stored runs to the current contract, or use a build that reads them.",
        ) from exc
    except StoreError as exc:
        raise api_error(ApiErrorCode.STORE_ERROR, str(exc)) from exc
    except database_error_types() as exc:
        raise api_error(
            ApiErrorCode.STORE_UNAVAILABLE,
            "The database stopped answering.",
            hint="Check that it is running, then retry.",
        ) from exc
