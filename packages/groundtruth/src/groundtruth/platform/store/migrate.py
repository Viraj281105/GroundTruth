"""Apply and roll back schema migrations.

**Owner: Bhumi.**

Alembic is configured in code rather than only through ``alembic.ini`` so the same
functions serve the tests, a deploy step and the command line, and so migrations
work from an installed package where no ``.ini`` file sits next to the code.
"""

from __future__ import annotations

from pathlib import Path
from typing import TextIO

from alembic import command
from alembic.config import Config

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
