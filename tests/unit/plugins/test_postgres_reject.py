"""Reject and is_rejected in the PostgreSQL store, without a database (issue #92).

``Session`` is replaced with a minimal fake so the transaction logic, the audit
row and the deletion hook are exercised in the unit-test job.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

import pytest

from data.models import RejectedDocument
from plugins.relational_db import postgres
from plugins.relational_db.postgres import PostgreSQLStore, StoreDocumentNotFoundError

URL = "https://example.invalid/doc"


class _FakeResult:
    def __init__(self, value: Any) -> None:
        self._value = value

    def scalar_one_or_none(self) -> Any:
        return self._value

    def scalar(self) -> Any:
        return self._value


class _FakeSession:
    def __init__(self, value: Any) -> None:
        self.value = value
        self.added: list[Any] = []

    def __enter__(self) -> _FakeSession:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    @contextmanager
    def begin(self) -> Iterator[None]:
        yield

    def execute(self, stmt: object) -> _FakeResult:
        return _FakeResult(self.value)

    def add(self, obj: Any) -> None:
        self.added.append(obj)


def _store(
    monkeypatch: pytest.MonkeyPatch,
    value: Any,
    hook: Callable[[str], None] | None = None,
) -> tuple[PostgreSQLStore, _FakeSession]:
    store = PostgreSQLStore(on_document_deleted=hook)
    monkeypatch.setattr(store, "_ensure_initialized", lambda: None)
    session = _FakeSession(value)
    monkeypatch.setattr(postgres, "Session", lambda engine: session)
    return store, session


class _ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def test_reject_writes_audit_row_and_calls_hook(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    store, session = _store(monkeypatch, URL, hook=calls.append)

    store.reject("doc-1", "admin@example.invalid")

    assert len(session.added) == 1
    row = session.added[0]
    assert isinstance(row, RejectedDocument)
    assert row.document_id == "doc-1"
    assert row.source_url == URL
    assert row.admin == "admin@example.invalid"
    assert row.rejected_at.tzinfo is not None
    assert calls == ["doc-1"]


def test_reject_without_hook(monkeypatch: pytest.MonkeyPatch) -> None:
    store, session = _store(monkeypatch, URL)

    store.reject("doc-1", "admin")

    assert len(session.added) == 1


def test_reject_unknown_id_raises_and_writes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    store, session = _store(monkeypatch, None, hook=calls.append)

    with pytest.raises(StoreDocumentNotFoundError, match="missing"):
        store.reject("missing", "admin")

    assert session.added == []
    assert calls == []


def test_reject_logs_and_swallows_hook_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(document_id: str) -> None:
        raise RuntimeError("hook down")

    store, session = _store(monkeypatch, URL, hook=_boom)
    handler = _ListHandler()
    logger = logging.getLogger("plugins.relational_db.postgres")
    logger.addHandler(handler)
    try:
        store.reject("doc-1", "admin")
    finally:
        logger.removeHandler(handler)

    assert len(session.added) == 1
    errors = [r for r in handler.records if r.levelno == logging.ERROR]
    assert len(errors) == 1
    assert "doc-1" in errors[0].getMessage()
    assert errors[0].exc_info is not None


@pytest.mark.parametrize(("value", "expected"), [(True, True), (False, False), (None, False)])
def test_is_rejected(monkeypatch: pytest.MonkeyPatch, value: Any, expected: bool) -> None:
    store, _ = _store(monkeypatch, value)

    assert store.is_rejected(URL) is expected
