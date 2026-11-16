"""Worker shutdown closes the live store pool (issue #189, T3).

Unit tests mock the store; this test uses a real ``PostgreSQLStore`` built by
``_make_store`` and checks that ``worker_process_shutdown`` empties its pool.

Marked ``integration``: needs a live PostgreSQL at schema head. Skipped if it is unreachable.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from celery.signals import worker_process_shutdown
from sqlalchemy.pool import QueuePool

from tasks import fetch

pytestmark = pytest.mark.integration


@pytest.fixture
def no_store(postgres_url: str) -> Iterator[None]:
    """Start and end with no worker store; close a store the test leaves open."""
    fetch._store = None
    try:
        yield
    finally:
        leftover = fetch._store
        fetch._store = None
        if leftover is not None:
            leftover.close()


@pytest.mark.usefixtures("no_store")
def test_shutdown_closes_live_pool() -> None:
    store = fetch._make_store()
    assert store.get_document(str(uuid.uuid4())) is None
    assert store._engine is not None
    old_pool = store._engine.pool
    assert isinstance(old_pool, QueuePool)
    assert old_pool.checkedin() > 0

    worker_process_shutdown.send(sender=None)

    assert old_pool.checkedin() == 0
    assert store._engine is None
    assert fetch._store is None
