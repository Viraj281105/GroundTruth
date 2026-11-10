"""Database engine and session construction.

**Owner: Bhumi.**

Nothing here chooses a database for you. With no ``DATABASE_URL`` the platform has
nowhere to put results, and silently falling back to a local SQLite file would let a
deployment believe its results were durable when they were not (the same reasoning
as R7: a quiet fallback is a wrong answer served as if it were right).
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from groundtruth.contracts.errors import ConfigurationError
from groundtruth.platform.config import get_settings


def resolve_database_url(url: str | None = None) -> str:
    """Return ``url``, or ``Settings.database_url`` when none is given.

    Raises:
        ConfigurationError: if neither is set. The URL is never included in any
            message, because it can carry a password.
    """
    resolved = url or get_settings().database_url
    if not resolved:
        raise ConfigurationError(
            "no database configured: set DATABASE_URL, for example "
            "postgresql+psycopg://user:password@host/dbname"
        )
    return resolved


POSTGRES_CONNECT_TIMEOUT_S = 10
"""Seconds to wait for PostgreSQL to accept a connection (#48)."""


def create_db_engine(url: str | None = None, **kwargs: Any) -> Engine:
    """Create an engine for ``url`` (default: the configured database).

    SQLite ignores foreign keys unless asked per connection. They are switched on so
    the schema behaves the same in the SQLite test suite as on PostgreSQL.
    """
    resolved = resolve_database_url(url)
    if sa.engine.make_url(resolved).get_backend_name() == "postgresql":
        # A database that does not answer must fail the request, not hang it (#48).
        connect_args = {
            "connect_timeout": POSTGRES_CONNECT_TIMEOUT_S,
            **kwargs.get("connect_args", {}),
        }
        kwargs = {**kwargs, "connect_args": connect_args}
    engine = sa.create_engine(resolved, **kwargs)
    if engine.dialect.name == "sqlite":

        @sa.event.listens_for(engine, "connect")
        def _enable_foreign_keys(dbapi_connection: Any, _record: Any) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """A session factory that does not expire objects on commit.

    Stored rows are read-mostly values; expiring them on commit would turn the next
    attribute access into a surprise query.
    """
    return sessionmaker(engine, expire_on_commit=False)
