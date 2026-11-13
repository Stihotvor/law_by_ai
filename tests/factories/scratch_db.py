"""Throwaway PostgreSQL databases for migration tests, and tenant-scoped SQL helpers.

The bootstrap superuser (``POSTGRES_USER`` / ``POSTGRES_PASSWORD``) is test-only
here: it runs ``CREATE DATABASE`` and ``DROP DATABASE`` and nothing else. The new
database is owned by ``lawbyai_owner``, which migrates it. Assertions connect as
``lawbyai_app``. Roles are cluster-wide, so they exist in every database.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import pytest
from sqlalchemy import Engine, Row, create_engine, make_url, text
from sqlalchemy.exc import DBAPIError

from config.settings import OWNER_ROLE, get_settings

TENANT_SQL = "SELECT set_config('app.current_tenant', :tenant, true)"
# lawbyai_auth must own auth_lookup_user; docker/initdb/00-roles.sh grants this
# on the main database only. The scratch database owner grants it itself.
AUTH_SCHEMA_GRANT = "GRANT CREATE, USAGE ON SCHEMA public TO lawbyai_auth"


@dataclass(frozen=True)
class ScratchDb:
    """URLs of one scratch database: the app role and the owner role."""

    name: str
    app_url: str
    owner_url: str


def tenant_sql(url: str, tenant: str, sql: str, **params: Any) -> list[Row[Any]]:
    """Run *sql* in one transaction with ``app.current_tenant`` set to *tenant*."""
    engine = create_engine(url, future=True)
    try:
        with engine.begin() as conn:
            conn.execute(text(TENANT_SQL), {"tenant": tenant})
            result = conn.execute(text(sql), params)
            return list(result.all()) if result.returns_rows else []
    finally:
        engine.dispose()


def superuser_url() -> str:
    """Test-only URL of the bootstrap superuser, on the configured host and database."""
    settings = get_settings()
    url = make_url(settings.postgres_owner_url).set(
        username=settings.postgres_user, password=settings.postgres_password
    )
    return url.render_as_string(hide_password=False)


def _with_database(url: str, name: str) -> str:
    return make_url(url).set(database=name).render_as_string(hide_password=False)


def _autocommit(engine: Engine, sql: str) -> None:
    with engine.connect() as conn:
        conn.execute(text(sql))


@contextmanager
def scratch_database(prefix: str) -> Iterator[ScratchDb]:
    """Create an empty database owned by ``lawbyai_owner``; drop it on exit.

    Skips the test when the superuser cannot create it.
    """
    settings = get_settings()
    name = f"{prefix}_{uuid.uuid4().hex[:12]}"
    admin = create_engine(superuser_url(), isolation_level="AUTOCOMMIT")
    try:
        _autocommit(admin, f'CREATE DATABASE "{name}" OWNER {OWNER_ROLE}')
    except DBAPIError:
        admin.dispose()
        pytest.skip("cannot create a scratch database for migration tests")
    try:
        db = ScratchDb(
            name=name,
            app_url=_with_database(settings.postgres_url, name),
            owner_url=_with_database(settings.postgres_owner_url, name),
        )
        owner = create_engine(db.owner_url, isolation_level="AUTOCOMMIT")
        try:
            _autocommit(owner, AUTH_SCHEMA_GRANT)
        finally:
            owner.dispose()
        yield db
    finally:
        _autocommit(admin, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        admin.dispose()
