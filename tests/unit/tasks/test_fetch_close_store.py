"""Close handler ``_close_store`` for the worker store.

Unit tests: ``PostgreSQLStore`` is mocked, so no database or network is needed.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import cast
from unittest.mock import MagicMock

import pytest
from celery.signals import worker_process_shutdown

from tasks import fetch

CLOSE_FAILED = "store close failed"


@pytest.fixture(autouse=True)
def reset_store() -> Iterator[None]:
    fetch._store = None
    yield
    fetch._store = None


@pytest.fixture
def factory(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    mock = MagicMock(side_effect=lambda: MagicMock())
    monkeypatch.setattr(fetch, "PostgreSQLStore", mock)
    return mock


def _built_store() -> MagicMock:
    return cast(MagicMock, fetch._make_store())


def test_no_store_builds_nothing(factory: MagicMock) -> None:
    fetch._close_store()

    factory.assert_not_called()
    assert fetch._store is None


def test_one_store_is_closed_once(factory: MagicMock) -> None:
    store = _built_store()

    fetch._close_store()

    store.close.assert_called_once_with()
    assert fetch._store is None


def test_close_error_is_logged_and_swallowed(
    factory: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    store = _built_store()
    store.close.side_effect = RuntimeError("close failed")

    with caplog.at_level(logging.WARNING, logger="tasks.fetch"):
        fetch._close_store()

    records = [r for r in caplog.records if r.getMessage() == CLOSE_FAILED]
    assert len(records) == 1
    assert records[0].levelno == logging.WARNING
    assert records[0].exc_info is not None
    assert fetch._store is None


def test_cache_cleared_after_close(factory: MagicMock) -> None:
    first = fetch._make_store()
    fetch._close_store()

    second = fetch._make_store()

    assert factory.call_count == 2
    assert second is not first
    assert fetch._store is second


def test_failed_build_propagates_and_leaves_store_none(monkeypatch: pytest.MonkeyPatch) -> None:
    error = RuntimeError("schema not at head")
    monkeypatch.setattr(fetch, "PostgreSQLStore", MagicMock(side_effect=error))

    with pytest.raises(RuntimeError) as caught:
        fetch._make_store()

    assert caught.value is error
    assert fetch._store is None


def test_shutdown_signal_closes_store(factory: MagicMock) -> None:
    store = _built_store()

    worker_process_shutdown.send(sender=None, pid=1, exitcode=0)

    store.close.assert_called_once_with()
    assert fetch._store is None
