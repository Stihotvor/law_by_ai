"""Alembic migration environment (issue #9).

Connects to PostgreSQL as the owner role ``lawbyai_owner``. Uses the
``sqlalchemy.url`` already on the Alembic config (the init program passes the
owner URL); when it is empty, uses ``config.settings.postgres_owner_url``
(``POSTGRES_OWNER_URL`` / ``LAWBYAI_OWNER_PASSWORD`` + ``POSTGRES_*``). The app role ``lawbyai_app``
cannot migrate. Autogenerates against the SQLAlchemy models in
``plugins.relational_db.postgres`` (``Base.metadata``). Online runs hold a
PostgreSQL session advisory lock so concurrent upgrades apply each migration once.
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from logging.config import fileConfig

from alembic import context
from alembic.config import Config
from sqlalchemy import Connection, engine_from_config, pool, text

from config.settings import get_settings
from plugins.relational_db.postgres import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)


def _use_owner_url_if_unset(cfg: Config) -> None:
    """Keep a URL the caller set (e.g. the init program); else use the owner URL.

    Escape "%" (URL-quoted passwords) for configparser interpolation.
    """
    if not cfg.get_main_option("sqlalchemy.url"):
        cfg.set_main_option("sqlalchemy.url", get_settings().postgres_owner_url.replace("%", "%%"))


_use_owner_url_if_unset(config)

# Session advisory lock key ("law_mig" in ASCII) that serializes online upgrades.
MIGRATION_LOCK_KEY = 0x6C61775F6D6967

logger = logging.getLogger("alembic.env")

# Model's MetaData object for autogenerate support.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL, no DB connection)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


@contextmanager
def _migration_lock(connection: Connection) -> Iterator[None]:
    """Hold the session advisory lock; on release, log a failure and do not raise it.

    A failed release never hides the migration error. Closing the NullPool
    connection ends the session, which frees the lock anyway.
    """
    connection.execute(text("SELECT pg_advisory_lock(:key)"), {"key": MIGRATION_LOCK_KEY})
    try:
        # End the autobegun transaction. The session lock stays held, and Alembic
        # starts its own migration transaction.
        connection.commit()
        yield
    finally:
        try:
            if connection.in_transaction():
                connection.rollback()
            connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": MIGRATION_LOCK_KEY})
            connection.commit()
        except Exception:
            logger.exception("Could not release the migration advisory lock")


def run_migrations_online() -> None:
    """Run migrations in 'online' mode against a live engine."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection, _migration_lock(connection):
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
