"""PostgreSQLStore sizes its pool from the caller's PoolConfig or the app settings.

``create_engine`` does not connect, so a fake PostgreSQL URL gives a real
``QueuePool`` without a live database. The schema head check is replaced with
a no-op, and a spy records the ``create_engine`` keyword arguments.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import Engine
from sqlalchemy.pool import QueuePool

from config.settings import PoolConfig, get_settings
from plugins.relational_db import postgres
from plugins.relational_db.postgres import PostgreSQLStore

FAKE_URL = "postgresql+psycopg://user:pw@127.0.0.1:1/none"


@pytest.fixture
def engine_calls(clean_pool_env: pytest.MonkeyPatch) -> Iterator[list[dict[str, Any]]]:
    """Fake URL, no pool variables, no head check; record create_engine kwargs."""
    monkeypatch = clean_pool_env
    monkeypatch.setenv("POSTGRES_URL", FAKE_URL)
    monkeypatch.setattr(postgres, "_check_schema_head", lambda _engine: None)
    calls: list[dict[str, Any]] = []
    real_create_engine = postgres.create_engine

    def spy(url: str, **kwargs: Any) -> Engine:
        calls.append(kwargs)
        return real_create_engine(url, **kwargs)

    monkeypatch.setattr(postgres, "create_engine", spy)
    get_settings.cache_clear()
    yield calls
    get_settings.cache_clear()


def _pool(store: PostgreSQLStore) -> QueuePool:
    engine = store._engine
    assert engine is not None
    pool = engine.pool
    assert isinstance(pool, QueuePool)
    return pool


def test_worker_pool(engine_calls: list[dict[str, Any]]) -> None:
    """Scenario: Worker pool."""
    store = PostgreSQLStore(pool=PoolConfig(1, 1))

    store.initialize()

    assert _pool(store).size() == 1
    assert engine_calls[0]["max_overflow"] == 1
    store.close()


def test_default_app_pool(engine_calls: list[dict[str, Any]]) -> None:
    """Scenario: Default app pool."""
    store = PostgreSQLStore()

    store.initialize()

    assert _pool(store).size() == 5
    assert engine_calls[0]["max_overflow"] == 10
    store.close()


@pytest.mark.parametrize("pool", [None, PoolConfig(1, 1)])
def test_engine_options(engine_calls: list[dict[str, Any]], pool: PoolConfig | None) -> None:
    """Scenario: Engine options."""
    store = PostgreSQLStore(pool=pool)

    store.initialize()

    assert len(engine_calls) == 1
    assert engine_calls[0]["pool_pre_ping"] is True
    assert engine_calls[0]["pool_timeout"] == postgres.POOL_TIMEOUT_SECONDS == 30
    store.close()


def test_bad_app_setting(
    engine_calls: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: Bad app setting."""
    monkeypatch.setenv("POSTGRES_POOL_SIZE", "0")
    store = PostgreSQLStore()

    with pytest.raises(ValueError, match="POSTGRES_POOL_SIZE"):
        store.initialize()

    assert engine_calls == []


def test_constructor_does_not_read_settings(
    engine_calls: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: Constructor does not read settings."""
    monkeypatch.setenv("POSTGRES_POOL_SIZE", "0")

    PostgreSQLStore()
