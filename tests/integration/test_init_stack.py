"""Init program against a live PostgreSQL: two runs, one tenant, one admin.

Marked ``integration``. The store runs as ``lawbyai_app``; the init program
migrates with the owner URL; the owner checks and deletes rows inside the
init tenant. There is no S3 service in the integration job, so the
S3 client is a fake. Skipped if PostgreSQL is unreachable.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from factories.bootstrap import FakeBucket, FakeSettings
from factories.db_probe import can_connect
from factories.scratch_db import tenant_sql

from bootstrap.init_stack import run
from config.settings import get_settings
from core.security import ADMIN, tenant_context
from plugins.relational_db.postgres import PostgreSQLStore

pytestmark = pytest.mark.integration


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeSettings]:
    """Give settings with a unique tenant and admin, and delete them afterwards."""
    url = get_settings().postgres_url
    owner_url = get_settings().postgres_owner_url
    if not (can_connect(url) and can_connect(owner_url)):
        pytest.skip("PostgreSQL unavailable")
    monkeypatch.setenv("BCRYPT_ROUNDS", "4")
    suffix = uuid.uuid4().hex[:12]
    fake = FakeSettings(
        postgres_url=url,
        postgres_owner_url=owner_url,
        init_tenant_id=f"init-{suffix}",
        init_admin_email=f"init-{suffix}@example.com",
    )
    yield fake
    _cleanup(fake)


def _cleanup(settings: FakeSettings) -> None:
    """Delete the init admin and tenant as the owner, inside the init tenant."""
    owner_url, tenant = settings.postgres_owner_url, settings.init_tenant_id
    email = settings.init_admin_email
    tenant_sql(owner_url, tenant, "DELETE FROM users WHERE email = :e", e=email)
    tenant_sql(owner_url, tenant, "DELETE FROM tenants WHERE id = :t", t=tenant)


def _run_twice(settings: FakeSettings) -> None:
    """Run the init program twice, each time with a new store."""
    client = FakeBucket()
    for _ in range(2):
        store = PostgreSQLStore()
        try:
            assert run(settings, store, client) == 0
        finally:
            store.close()


def _count(settings: FakeSettings, sql: str, value: str) -> int:
    """Return the number of rows the count query finds for the value, in the init tenant."""
    rows = tenant_sql(settings.postgres_url, settings.init_tenant_id, sql, v=value)
    return int(rows[0][0])


def test_run_twice_creates_one_tenant_and_one_admin(settings: FakeSettings) -> None:
    """Check that two runs create exactly one tenant and one admin."""
    _run_twice(settings)
    tenant = settings.init_tenant_id
    assert _count(settings, "SELECT count(*) FROM tenants WHERE id = :v", tenant) == 1
    assert (
        _count(settings, "SELECT count(*) FROM users WHERE email = :v", settings.init_admin_email)
        == 1
    )
    store = PostgreSQLStore()
    try:
        with tenant_context(tenant):
            user = store.get_user_by_email(settings.init_admin_email)
    finally:
        store.close()
    assert user is not None
    assert user["role"] == ADMIN
    assert user["tenant_id"] == tenant


def test_cleanup_removes_tenant_and_admin(settings: FakeSettings) -> None:
    """Check that the fixture cleanup leaves no tenant and no admin behind."""
    _run_twice(settings)

    _cleanup(settings)

    tenant = settings.init_tenant_id
    assert _count(settings, "SELECT count(*) FROM tenants WHERE id = :v", tenant) == 0
    assert (
        _count(settings, "SELECT count(*) FROM users WHERE email = :v", settings.init_admin_email)
        == 0
    )
