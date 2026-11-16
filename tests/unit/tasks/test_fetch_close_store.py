"""Close handler ``_close_store`` for the worker store.

Unit tests: ``PostgreSQLStore`` is mocked, so no database or network is needed.
"""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock

import pytest
from celery.signals import worker_process_shutdown

from tasks import fetch
from tasks.celery_app import FETCH_DOCUMENT, app

pytestmark = pytest.mark.usefixtures("reset_store")

CLOSE_FAILED = "store close failed"


@pytest.fixture
def factory(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    mock = MagicMock(side_effect=lambda **_: MagicMock())
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


def test_qa_005_store_dropped_when_close_fails(factory: MagicMock) -> None:
    _built_store().close.side_effect = RuntimeError("socket gone")
    fetch._close_store()

    fetch._make_store()

    assert factory.call_count == 2


def test_qa_008_failed_build_is_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    good = MagicMock()
    monkeypatch.setattr(
        fetch, "PostgreSQLStore", MagicMock(side_effect=[RuntimeError("not at head"), good])
    )
    with pytest.raises(RuntimeError):
        fetch._make_store()

    assert fetch._make_store() is good
    assert fetch._store is good


def test_qa_009_shutdown_after_failed_build_closes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fetch, "PostgreSQLStore", MagicMock(side_effect=RuntimeError("x")))
    with pytest.raises(RuntimeError):
        fetch._make_store()

    fetch._close_store()

    assert fetch._store is None


def test_qa_013_repeated_shutdown_closes_once(factory: MagicMock) -> None:
    store = _built_store()

    worker_process_shutdown.send(sender=None)
    worker_process_shutdown.send(sender=None)

    store.close.assert_called_once_with()


def test_qa_015_extra_signal_arguments(factory: MagicMock) -> None:
    store = _built_store()

    worker_process_shutdown.send(sender="ForkPoolWorker-3", pid=4242, exitcode=0)

    store.close.assert_called_once_with()


def test_qa_014_import_builds_no_store(monkeypatch: pytest.MonkeyPatch) -> None:
    source_class = MagicMock()
    monkeypatch.setattr("plugins.relational_db.postgres.PostgreSQLStore", source_class)
    spec = importlib.util.spec_from_file_location("tasks._fetch_import_copy", fetch.__file__)
    assert spec is not None
    assert spec.loader is not None
    copy = importlib.util.module_from_spec(spec)
    # The copy re-registers the task under the same name; restore the original after.
    original_task = app.tasks[FETCH_DOCUMENT]

    try:
        spec.loader.exec_module(copy)
        source_class.assert_not_called()
        assert copy._store is None
    finally:
        worker_process_shutdown.disconnect(copy._close_store)
        app.tasks[FETCH_DOCUMENT] = original_task


def test_qa_016_migration_comment_says_init_service() -> None:
    lines = [ln for ln in Path(fetch.__file__).read_text().splitlines() if "migrat" in ln]

    assert lines
    assert all("init service" in ln or "never migrate" in ln.lower() for ln in lines)
