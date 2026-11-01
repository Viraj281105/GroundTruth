"""Where the stored-run endpoints get their evidence store.

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

from groundtruth.contracts.errors import ConfigurationError
from groundtruth.platform.api.errors import ApiErrorCode, api_error
from groundtruth.platform.store.interface import EvidenceStore

_lock = threading.Lock()
_store: EvidenceStore | None = None


def get_store() -> EvidenceStore:
    """The process's evidence store, built on first use.

    A successful build is kept for the life of the process. A failed one is not: the
    next request tries again, so fixing the configuration needs no restart of the
    request path.

    Raises:
        HTTPException: 503 ``store_not_configured`` or ``store_unavailable``.
    """
    global _store
    if _store is not None:
        return _store
    with _lock:
        if _store is None:
            _store = _build_store()
        return _store


def reset_store() -> None:
    """Forget the cached store. For tests."""
    global _store
    with _lock:
        _store = None


def _build_store() -> EvidenceStore:
    try:
        import sqlalchemy as sa

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
    return SqlEvidenceStore(create_session_factory(create_db_engine(url)))


def database_error_types() -> tuple[type[Exception], ...]:
    """Exceptions meaning "the database stopped answering", for the routes to catch.

    Empty when SQLAlchemy is not installed, which also means no store was ever built.
    """
    try:
        import sqlalchemy as sa
    except ImportError:
        return ()
    return (sa.exc.OperationalError, sa.exc.InterfaceError)
