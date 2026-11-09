"""Opt-in PostgreSQL for the database-backed tests.

By default every test uses its own temporary SQLite file, exactly as before. If the environment
variable ``GT_TEST_PG_ADMIN_URL`` names an *isolated, disposable* PostgreSQL server (for example
``postgresql+psycopg://gt_test:pw@127.0.0.1:55432/postgres``), each test instead gets its own
freshly created database on that server, dropped afterwards, so the same suites run unchanged on
PostgreSQL. Never point this at a database that holds data you care about.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

import sqlalchemy as sa

ADMIN_ENV = "GT_TEST_PG_ADMIN_URL"


def using_postgres() -> bool:
    return bool(os.environ.get(ADMIN_ENV))


class TestDatabase:
    """A database for one test: ``url`` to connect, ``connect_args`` for the engine, ``drop()``."""

    __test__ = False  # not a pytest class

    def __init__(self, url: str, connect_args: dict[str, Any], dropper: Any = None) -> None:
        self.url = url
        self.connect_args = connect_args
        self._dropper = dropper

    def drop(self) -> None:
        if self._dropper is not None:
            self._dropper()


def new_database(tmp_path: Path, sqlite_name: str = "test.db") -> TestDatabase:
    admin = os.environ.get(ADMIN_ENV)
    if not admin:
        return TestDatabase(f"sqlite:///{tmp_path / sqlite_name}", {"timeout": 30})

    name = f"gt_t_{uuid.uuid4().hex[:12]}"
    engine = sa.create_engine(admin, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        conn.execute(sa.text(f'CREATE DATABASE "{name}"'))
    url = sa.engine.make_url(admin).set(database=name).render_as_string(hide_password=False)

    def drop() -> None:
        with engine.connect() as conn:
            conn.execute(
                sa.text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :n AND pid <> pg_backend_pid()"
                ),
                {"n": name},
            )
            conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{name}"'))
        engine.dispose()

    return TestDatabase(url, {}, drop)
