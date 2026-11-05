"""Init program against a live PostgreSQL: two runs, one tenant, one admin.

Marked ``integration``. There is no S3 service in the integration job, so the
S3 client is a fake. Skipped if PostgreSQL is unreachable.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from factories.bootstrap import FakeBucket, FakeSettings
from sqlalchemy import create_engine, text

from bootstrap.init_stack import run
from config.settings import get_settings
from core.security import ADMIN
from plugins.relational_db.postgres import PostgreSQLStore

pytestmark = pytest.mark.integration


def _can_connect(url: str) -> bool:
    try:
        engine = create_engine(url, future=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return True
    except Exception:
        return False


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeSettings]:
    url = get_settings().postgres_url
    if not _can_connect(url):
        pytest.skip("PostgreSQL unavailable")
    monkeypatch.setenv("BCRYPT_ROUNDS", "4")
    suffix = uuid.uuid4().hex[:12]
    fake = FakeSettings(
        postgres_url=url,
        init_tenant_id=f"init-{suffix}",
        init_admin_email=f"init-{suffix}@example.com",
    )
    yield fake
    engine = create_engine(url, future=True)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM users WHERE email = :e"), {"e": fake.init_admin_email})
        conn.execute(text("DELETE FROM tenants WHERE id = :t"), {"t": fake.init_tenant_id})
    engine.dispose()


def _count(url: str, sql: str, value: str) -> int:
    engine = create_engine(url, future=True)
    with engine.connect() as conn:
        count = conn.execute(text(sql), {"v": value}).scalar_one()
    engine.dispose()
    return int(count)


def test_run_twice_creates_one_tenant_and_one_admin(settings: FakeSettings) -> None:
    client = FakeBucket()
    for _ in range(2):
        store = PostgreSQLStore()
        try:
            assert run(settings, store, client) == 0
        finally:
            store.close()
    url = settings.postgres_url
    assert _count(url, "SELECT count(*) FROM tenants WHERE id = :v", settings.init_tenant_id) == 1
    assert (
        _count(url, "SELECT count(*) FROM users WHERE email = :v", settings.init_admin_email) == 1
    )
    store = PostgreSQLStore()
    try:
        user = store.get_user_by_email(settings.init_admin_email)
    finally:
        store.close()
    assert user is not None
    assert user["role"] == ADMIN
    assert user["tenant_id"] == settings.init_tenant_id
