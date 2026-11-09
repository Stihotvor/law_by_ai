"""Celery task ``fetch_document`` (issue #11).

Unit tests: the store and the fetcher are mocked, so no database or network is needed.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest

from agents.fetch.contracts import DocumentMeta, DocumentRef, FetchedDocument
from agents.fetch.errors import DocumentRejectedError, FetchTransportError
from agents.fetch.formats.base import FormatError
from tasks import fetch
from tasks.celery_app import app

SOURCE = "test-source"
URL = "https://example.test/doc/1"
FETCHED_AT = datetime(2026, 1, 2, tzinfo=UTC)


def _fetched(tenant_id: str | None = None) -> FetchedDocument:
    ref = DocumentRef(source=SOURCE, external_id=URL, url=URL)
    meta = DocumentMeta(ref=ref, title="Act 1", extra={"k": "v"})
    return FetchedDocument(
        meta=meta,
        content=b"raw",
        content_type="text/plain",
        fetched_at=FETCHED_AT,
        tenant_id=tenant_id,
    )


@pytest.fixture(autouse=True)
def eager() -> Iterator[None]:
    old = (app.conf.task_always_eager, app.conf.task_eager_propagates)
    app.conf.task_always_eager = True
    app.conf.task_eager_propagates = True
    yield
    app.conf.task_always_eager, app.conf.task_eager_propagates = old


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    mock = MagicMock()
    mock.save_document.return_value = "doc-1"
    monkeypatch.setattr(fetch, "_make_store", lambda: mock)
    return mock


@pytest.fixture
def agent(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    mock = MagicMock()
    mock.fetch_document.return_value = _fetched()
    mock.parse.return_value = "parsed text"
    monkeypatch.setattr(fetch, "_make_agent", lambda rejection: mock)
    return mock


def _run(tenant_id: str | None = None) -> Any:
    return app.tasks["fetch_document"].delay(SOURCE, URL, tenant_id=tenant_id).get()


def test_task_is_registered() -> None:
    assert "tasks.fetch" in app.conf.include
    app.loader.import_default_modules()
    assert "fetch_document" in app.tasks


def test_eager_call_saves_one_document(store: MagicMock, agent: MagicMock) -> None:
    result = _run()

    assert result == {"status": "saved", "document_id": "doc-1", "source_url": URL}
    store.save_document.assert_called_once()
    document = store.save_document.call_args.args[0]
    assert document["source_url"] == URL


def test_saved_document_fields(store: MagicMock, agent: MagicMock) -> None:
    _run(tenant_id="t1")

    document, tenant = store.save_document.call_args.args
    assert tenant == "t1"
    assert document == {
        "title": "Act 1",
        "content": "parsed text",
        "source": SOURCE,
        "source_url": URL,
        "last_updated": FETCHED_AT,
        "metadata": {"k": "v"},
        "is_processed": False,
        "status": "needs_review",
    }


def test_agent_gets_ref_tenant_and_parse_args(store: MagicMock, agent: MagicMock) -> None:
    _run(tenant_id="t1")

    ref = DocumentRef(source=SOURCE, external_id=URL, url=URL)
    agent.fetch_document.assert_called_once_with(SOURCE, ref, tenant_id="t1")
    agent.parse.assert_called_once_with(b"raw", URL, "text/plain")


def test_fetch_error_reaches_caller_and_saves_nothing(store: MagicMock, agent: MagicMock) -> None:
    agent.fetch_document.side_effect = FetchTransportError("down")

    with pytest.raises(FetchTransportError):
        _run()

    store.save_document.assert_not_called()
    agent.close.assert_called_once()


def test_rejected_document_is_skipped(store: MagicMock, agent: MagicMock) -> None:
    agent.fetch_document.side_effect = DocumentRejectedError("rejected")

    assert _run() == {"status": "skipped", "source_url": URL}
    store.save_document.assert_not_called()
    agent.parse.assert_not_called()
    agent.close.assert_called_once()


def test_parse_error_reaches_caller_and_saves_nothing(store: MagicMock, agent: MagicMock) -> None:
    agent.parse.side_effect = FormatError("bad format")

    with pytest.raises(FormatError):
        _run()

    store.save_document.assert_not_called()
    agent.close.assert_called_once()


def test_save_error_reaches_caller(store: MagicMock, agent: MagicMock) -> None:
    error = RuntimeError("db down")
    store.save_document.side_effect = error

    with pytest.raises(RuntimeError) as caught:
        _run()

    assert caught.value is error
    agent.close.assert_called_once()


def test_agent_closed_after_success(store: MagicMock, agent: MagicMock) -> None:
    _run()

    agent.close.assert_called_once()


def test_close_error_keeps_saved_result(
    store: MagicMock, agent: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    agent.close.side_effect = RuntimeError("close failed")

    with caplog.at_level(logging.WARNING, logger="tasks.fetch"):
        result = _run()

    assert result == {"status": "saved", "document_id": "doc-1", "source_url": URL}
    store.save_document.assert_called_once()
    assert "fetch agent close failed" in caplog.text


def test_close_error_keeps_skipped_result(
    store: MagicMock, agent: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    agent.fetch_document.side_effect = DocumentRejectedError("rejected")
    agent.close.side_effect = RuntimeError("close failed")

    with caplog.at_level(logging.WARNING, logger="tasks.fetch"):
        result = _run()

    assert result == {"status": "skipped", "source_url": URL}
    assert "fetch agent close failed" in caplog.text


def test_make_agent_uses_store_as_rejection_checker() -> None:
    checker = MagicMock()
    checker.is_rejected.return_value = True
    built = fetch._make_agent(checker)
    try:
        ref = DocumentRef(source=SOURCE, external_id=URL, url=URL)
        with pytest.raises(DocumentRejectedError):
            built.fetch_document(SOURCE, ref)
        checker.is_rejected.assert_called_once_with(URL)
    finally:
        built.close()


def test_make_store_is_built_once_without_db(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[object] = []

    class _Store:
        def __init__(self) -> None:
            created.append(self)

    monkeypatch.setattr(fetch, "PostgreSQLStore", _Store)
    fetch._make_store.cache_clear()
    try:
        first = fetch._make_store()
        assert fetch._make_store() is first
        assert created == [first]
    finally:
        fetch._make_store.cache_clear()
