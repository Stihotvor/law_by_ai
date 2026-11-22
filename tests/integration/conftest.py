"""Shared fixtures for integration tests: PostgreSQL URLs, Redis and eager Celery.

Tests connect as ``lawbyai_app`` (``postgres_url``). The owner ``lawbyai_owner``
(``owner_url``) only sets up and cleans data. FORCE row level security on
``tenants`` and ``users`` binds the owner too, so ``owner_sql`` sets the tenant
in each transaction.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

import pytest
import redis
from factories.db_probe import can_connect
from factories.scratch_db import tenant_sql
from redis.exceptions import AuthenticationError
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError
from sqlalchemy import Row
from users_helpers import CreateKeys

from config.settings import get_settings
from tasks.celery_app import app

OwnerSql = Callable[..., list[Row[Any]]]


@pytest.fixture
def postgres_url() -> str:
    """Return the app URL (``lawbyai_app``); skip only when the host is unreachable.

    A wrong password or a missing role fails the test.
    """
    url = get_settings().postgres_url
    if not can_connect(url):
        pytest.skip("PostgreSQL host unreachable")
    return url


@pytest.fixture
def owner_url() -> str:
    """Return the owner URL (``lawbyai_owner``); skip only when the host is unreachable.

    A wrong password or a missing role fails the test.
    """
    url = get_settings().postgres_owner_url
    if not can_connect(url):
        pytest.skip("PostgreSQL host unreachable (owner URL)")
    return url


@pytest.fixture
def owner_sql(owner_url: str) -> OwnerSql:
    """Return ``run(tenant, sql, **params)``: SQL as the owner inside a tenant context."""

    def run(tenant: str, sql: str, **params: Any) -> list[Row[Any]]:
        return tenant_sql(owner_url, tenant, sql, **params)

    return run


@pytest.fixture
def redis_client() -> Iterator[CreateKeys]:
    """Live Redis from ``settings.redis_url``; skip only when the host is unreachable.

    A wrong password fails the test. Tracked user-create keys are deleted before and after.
    """
    client = redis.Redis.from_url(
        get_settings().redis_url, socket_timeout=1, socket_connect_timeout=1
    )
    try:
        client.ping()
    except AuthenticationError:
        raise
    except (RedisConnectionError, RedisTimeoutError):
        client.close()
        pytest.skip("Redis host unreachable")
    keys = CreateKeys(client)
    try:
        yield keys
    finally:
        keys.clean()
        client.close()


@pytest.fixture
def eager_celery() -> Iterator[None]:
    """Run Celery tasks in process and raise their errors."""
    old = (app.conf.task_always_eager, app.conf.task_eager_propagates)
    app.conf.task_always_eager = True
    app.conf.task_eager_propagates = True
    yield
    app.conf.task_always_eager, app.conf.task_eager_propagates = old
