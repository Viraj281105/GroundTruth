"""Alembic environment: connects migrations to the configured database."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import context

from groundtruth.platform.store.database import resolve_database_url
from groundtruth.platform.store.models import Base

config = context.config
target_metadata = Base.metadata


def _url() -> str:
    # Set by migrate.alembic_config; absent when run through the alembic CLI, in
    # which case the URL comes from DATABASE_URL like everywhere else.
    configured = config.get_main_option("sqlalchemy.url")
    return resolve_database_url(configured.replace("%%", "%") if configured else None)


def run_migrations_offline() -> None:
    """Emit SQL to the output buffer instead of connecting (``--sql``)."""
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live connection."""
    engine = sa.create_engine(_url(), poolclass=sa.pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
