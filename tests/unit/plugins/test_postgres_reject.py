"""Reject and is_rejected in the PostgreSQL store, without a database (issue #92).

``Session`` is replaced with a minimal fake so the transaction logic, the audit
row and the deletion hook are exercised in the unit-test job.
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

import pytest

from core.security import PrincipalRequiredError, RequestPrincipal, principal_context
from data.models import RejectedDocument
from plugins.relational_db import postgres
from plugins.relational_db.postgres import PostgreSQLStore, StoreDocumentNotFoundError

URL = "https://example.invalid/doc"
ADMIN_PRINCIPAL = RequestPrincipal(email="admin@example.invalid", role="admin")


@pytest.fixture
def admin_principal() -> Iterator[None]:
    with principal_context(ADMIN_PRINCIPAL):
        yield


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


def _forbid_db(monkeypatch: pytest.MonkeyPatch) -> tuple[PostgreSQLStore, list[str]]:
    opened: list[str] = []
    store = PostgreSQLStore()
    monkeypatch.setattr(store, "_ensure_initialized", lambda: opened.append("engine"))
    monkeypatch.setattr(postgres, "Session", lambda engine: opened.append("session"))
    return store, opened


def test_reject_without_principal_raises_before_db(monkeypatch: pytest.MonkeyPatch) -> None:
    store, opened = _forbid_db(monkeypatch)

    with principal_context(None), pytest.raises(PrincipalRequiredError):
        store.reject("doc-1")

    assert opened == []


def test_reject_non_admin_principal_raises_before_db(monkeypatch: pytest.MonkeyPatch) -> None:
    store, opened = _forbid_db(monkeypatch)
    user = RequestPrincipal(email="u@x.pl", role="user")

    with principal_context(user), pytest.raises(PrincipalRequiredError):
        store.reject("doc-1")

    assert opened == []


def test_reject_signature_has_no_admin_parameter() -> None:
    assert "admin" not in inspect.signature(PostgreSQLStore.reject).parameters


def test_reject_actor_comes_from_principal(monkeypatch: pytest.MonkeyPatch) -> None:
    store, session = _store(monkeypatch, URL)

    with principal_context(RequestPrincipal(email=" a@x.pl ", role="admin")):
        store.reject("doc-1")

    assert [row.admin for row in session.added] == ["a@x.pl"]


@pytest.mark.usefixtures("admin_principal")
def test_reject_writes_audit_row_and_calls_hook(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    store, session = _store(monkeypatch, URL, hook=calls.append)

    store.reject("doc-1")

    assert len(session.added) == 1
    row = session.added[0]
    assert isinstance(row, RejectedDocument)
    assert row.document_id == "doc-1"
    assert row.source_url == URL
    assert row.admin == "admin@example.invalid"
    assert row.rejected_at.tzinfo is not None
    assert calls == ["doc-1"]


def test_reject_after_context_exit_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    store, session = _store(monkeypatch, URL)

    with principal_context(ADMIN_PRINCIPAL):
        store.reject("doc-011")
    with pytest.raises(PrincipalRequiredError):
        store.reject("doc-012")

    assert [row.document_id for row in session.added] == ["doc-011"]


def test_nested_context_restores_outer_actor(monkeypatch: pytest.MonkeyPatch) -> None:
    store, session = _store(monkeypatch, URL)
    outer = RequestPrincipal(email="a@example.com", role="admin")
    inner = RequestPrincipal(email="b@example.com", role="admin")

    with principal_context(outer):
        with principal_context(inner):
            pass
        store.reject("doc-014")

    assert [row.admin for row in session.added] == ["a@example.com"]


@pytest.mark.usefixtures("admin_principal")
def test_reject_without_hook(monkeypatch: pytest.MonkeyPatch) -> None:
    store, session = _store(monkeypatch, URL)

    store.reject("doc-1")

    assert len(session.added) == 1


@pytest.mark.usefixtures("admin_principal")
def test_reject_unknown_id_raises_and_writes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    store, session = _store(monkeypatch, None, hook=calls.append)

    with pytest.raises(StoreDocumentNotFoundError, match="missing"):
        store.reject("missing")

    assert session.added == []
    assert calls == []


@pytest.mark.usefixtures("admin_principal")
def test_reject_logs_and_swallows_hook_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(document_id: str) -> None:
        raise RuntimeError("hook down")

    store, session = _store(monkeypatch, URL, hook=_boom)
    handler = _ListHandler()
    logger = logging.getLogger("plugins.relational_db.postgres")
    logger.addHandler(handler)
    try:
        store.reject("doc-1")
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
