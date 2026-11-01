"""Apply and roll back schema migrations.

**Owner: Bhumi.**

Alembic is configured in code rather than only through ``alembic.ini`` so the same
functions serve the tests, a deploy step and the command line, and so migrations
work from an installed package where no ``.ini`` file sits next to the code.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TextIO

import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

from groundtruth.platform.store.database import resolve_database_url

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def alembic_config(url: str | None = None, *, output_buffer: TextIO | None = None) -> Config:
    """Build the Alembic configuration for ``url`` (default: the configured database).

    Args:
        url: Database URL. Defaults to ``Settings.database_url``.
        output_buffer: Where offline (``sql=True``) migrations write their SQL.
    """
    config = Config(output_buffer=output_buffer)
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    # configparser treats '%' as interpolation, and URL-encoded passwords contain it.
    config.set_main_option("sqlalchemy.url", resolve_database_url(url).replace("%", "%%"))
    return config


def upgrade(url: str | None = None, revision: str = "head") -> None:
    """Migrate the database forward to ``revision`` (default: the latest)."""
    command.upgrade(alembic_config(url), revision)


def downgrade(url: str | None = None, revision: str = "base") -> None:
    """Roll the database back to ``revision`` (default: an empty schema)."""
    command.downgrade(alembic_config(url), revision)


def head_revision() -> str:
    """The newest migration this code ships."""
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    head = ScriptDirectory.from_config(config).get_current_head()
    assert head is not None  # the package always ships at least one revision
    return head


@contextmanager
def _quiet_alembic() -> Iterator[None]:
    """Hide Alembic's INFO chatter during a read-only check; migrations stay audible."""
    alembic_logger = logging.getLogger("alembic")
    previous = alembic_logger.level
    alembic_logger.setLevel(logging.WARNING)
    try:
        yield
    finally:
        alembic_logger.setLevel(previous)


def current_revision(url: str | None = None) -> str | None:
    """The migration the database is at, or ``None`` if it has never been migrated."""
    engine = sa.create_engine(resolve_database_url(url))
    try:
        with _quiet_alembic(), engine.connect() as connection:
            return MigrationContext.configure(connection).get_current_revision()
    finally:
        engine.dispose()


def is_at_head(url: str | None = None) -> bool:
    """True if the database has every migration this code expects.

    Processes check this at startup and refuse to run against an older schema, rather
    than failing later with a missing column halfway through a job.
    """
    return current_revision(url) == head_revision()
