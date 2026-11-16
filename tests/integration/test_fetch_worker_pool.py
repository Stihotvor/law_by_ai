"""Celery task ``fetch_document`` with the worker pool (1 + 1) and a real PostgreSQL store.

Only the document source is fake; the store is the real one built by ``_make_store``.

Marked ``integration``: needs a live PostgreSQL. Skipped if it is unreachable.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fakes.fetch import FAKE_SOURCE, FAKE_STRATEGY, FakeSource, FakeStrategy
from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool

from agents.fetch.registry import Registry
from agents.fetch.sources.base import LegalSource, _validate_source
from agents.fetch.strategies.base import FetchStrategy
from tasks import fetch
from tasks.celery_app import app

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("eager_celery")]

_BASE = FakeSource.base_url


def _row_count(postgres_url: str, source_url: str) -> int:
    """Return the number of ``legal_document`` rows with *source_url*."""
    engine = create_engine(postgres_url, future=True)
    with engine.connect() as conn:
        count = conn.execute(
            text("SELECT count(*) FROM legal_document WHERE source_url = :u"), {"u": source_url}
        ).scalar_one()
    engine.dispose()
    return int(count)


@pytest.fixture(autouse=True)
def registries(monkeypatch: pytest.MonkeyPatch) -> None:
    """Swap in local registries holding the shared fakes."""
    sources: Registry[type[LegalSource]] = Registry("sources", _validate_source)
    strategies: Registry[type[FetchStrategy]] = Registry("strategies")
    sources.register(FAKE_SOURCE)(FakeSource)
    strategies.register(FAKE_STRATEGY)(FakeStrategy)
    monkeypatch.setattr("agents.fetch.document_fetcher.SOURCES", sources)
    monkeypatch.setattr("agents.fetch.document_fetcher.STRATEGIES", strategies)


@pytest.fixture
def source_url(postgres_url: str) -> Iterator[str]:
    """Unique source URL; its document and audit rows are removed afterwards."""
    value = f"{_BASE}/{uuid.uuid4().hex}.txt"
    yield value
    engine = create_engine(postgres_url, future=True)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM legal_document WHERE source_url = :u"), {"u": value})
        conn.execute(text("DELETE FROM rejected_document WHERE source_url = :u"), {"u": value})
    engine.dispose()


@pytest.fixture
def worker_pool(source_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Worker pool 1 + 1 and no cached store; the store the task builds is closed after."""
    monkeypatch.setenv("WORKER_POSTGRES_POOL_SIZE", "1")
    monkeypatch.setenv("WORKER_POSTGRES_MAX_OVERFLOW", "1")
    monkeypatch.setattr(fetch, "_store", None)
    try:
        yield
    finally:
        fetch._close_store()


def _run(source_url: str) -> Any:
    external_id = source_url.removeprefix(f"{_BASE}/")
    return app.tasks["fetch_document"].delay(FAKE_SOURCE, external_id).get()


@pytest.mark.usefixtures("worker_pool")
def test_fetch_document_worker_pool(postgres_url: str, source_url: str) -> None:
    result = _run(source_url)

    assert result["status"] == "saved"
    assert _row_count(postgres_url, source_url) == 1
    store = fetch._store
    assert store is not None
    engine = store._engine
    assert engine is not None
    pool = engine.pool
    assert isinstance(pool, QueuePool)
    assert pool.size() == 1
    assert pool._max_overflow == 1
    assert pool.checkedout() == 0
    assert pool.checkedin() <= 2
