"""Tenant write guard on ``save_document`` and ``update_document`` (unit level).

A fake ``Session`` stands in for PostgreSQL. The integration twin in
``tests/integration/plugins/test_postgres_tenant_guard.py`` runs the QA cases
on a live database.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest
from sqlalchemy.orm.exc import StaleDataError

from core.security import tenant_context
from data.models import LegalDocument
from plugins.relational_db import postgres
from plugins.relational_db.postgres import (
    PostgreSQLStore,
    StoreDocumentNotFoundError,
    _require_writable,
    _resolve_tenant,
)


def _row(tenant: str | None = "A", **overrides: Any) -> LegalDocument:
    fields: dict[str, Any] = {
        "id": "d1",
        "title": "t",
        "content": "c",
        "source": "s",
        "source_url": "u",
        "is_processed": False,
        "tenant_id": tenant,
        "status": "needs_review",
    }
    return LegalDocument(**{**fields, **overrides})


class FakeSession:
    """Fake session: ``get`` returns *row* and records its kwargs."""

    def __init__(self, row: LegalDocument | None, commit_error: Exception | None = None) -> None:
        self.row = row
        self.commit_error = commit_error
        self.added: list[Any] = []
        self.get_kwargs: list[dict[str, Any]] = []
        self.commits = 0
        self.rollbacks = 0

    def __enter__(self) -> FakeSession:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def get(self, _model: object, _key: str, **kwargs: Any) -> LegalDocument | None:
        self.get_kwargs.append(kwargs)
        return self.row

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    def commit(self) -> None:
        if self.commit_error is not None:
            raise self.commit_error
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def _store(monkeypatch: pytest.MonkeyPatch, session: FakeSession) -> PostgreSQLStore:
    store = PostgreSQLStore()
    monkeypatch.setattr(store, "_ensure_initialized", lambda: None)
    monkeypatch.setattr(postgres, "Session", lambda _engine: session)
    return store


def _doc(**extra: Any) -> dict[str, Any]:
    return {"title": "t", "content": "c", "source": "s", "source_url": "u", **extra}


def _warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]


# --- _resolve_tenant ---------------------------------------------------------


@pytest.mark.parametrize(
    ("arg", "context", "expected"),
    [
        (None, None, None),
        ("", None, None),
        (None, "", None),
        ("", "", None),
        (None, "A", "A"),
        ("", "A", "A"),
        ("A", None, "A"),
        ("A", "B", "A"),
    ],
)
def test_resolve_tenant(arg: str | None, context: str | None, expected: str | None) -> None:
    with tenant_context(context):
        assert _resolve_tenant(arg) == expected


# --- _require_writable -------------------------------------------------------


@pytest.mark.parametrize(
    ("row_tenant", "caller"), [("A", "A"), (None, None)], ids=["same-tenant", "shared-no-tenant"]
)
def test_require_writable_returns_owned_row(row_tenant: str | None, caller: str | None) -> None:
    row = _row(row_tenant)
    assert _require_writable(row, "d1", caller) is row


@pytest.mark.parametrize(
    ("row_tenant", "caller"),
    [("B", "A"), (None, "A"), ("A", None)],
    ids=["foreign", "shared-for-tenant", "tenant-row-for-no-tenant"],
)
def test_require_writable_rejects_foreign_row(row_tenant: str | None, caller: str | None) -> None:
    with pytest.raises(StoreDocumentNotFoundError) as info:
        _require_writable(_row(row_tenant), "d1", caller)
    assert str(info.value) == "Document not found: d1"


def test_require_writable_rejects_missing_row() -> None:
    with pytest.raises(StoreDocumentNotFoundError) as info:
        _require_writable(None, "d1", "A")
    assert str(info.value) == "Document not found: d1"


# --- StoreDocumentNotFoundError (QA-12) -------------------------------------


def test_not_found_error_is_key_error_with_plain_text() -> None:
    with pytest.raises(KeyError) as info:
        raise StoreDocumentNotFoundError("Document not found: d1")
    assert str(info.value) == "Document not found: d1"
    assert isinstance(info.value, LookupError)


# --- save_document ------------------------------------------------------------


def test_insert_uses_context_tenant_and_drops_payload_tenant(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    session = FakeSession(None)
    store = _store(monkeypatch, session)
    with tenant_context("A"), caplog.at_level(logging.WARNING, logger=postgres.__name__):
        store.save_document(_doc(tenant_id="B", status="approved"))
    assert session.added[0].tenant_id == "A"
    messages = _warnings(caplog)
    assert len(messages) == 1
    assert "tenant_id" in messages[0]
    assert "status" in messages[0]
    assert "'B'" not in messages[0]
    assert "approved" not in messages[0]


def test_insert_without_tenant_is_shared(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession(None)
    store = _store(monkeypatch, session)
    with tenant_context(None):
        store.save_document(_doc(tenant_id="B"))
    assert session.added[0].tenant_id is None


def test_insert_loads_with_for_update(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession(None)
    _store(monkeypatch, session).save_document(_doc(id="d1"))
    assert session.get_kwargs == [{"with_for_update": True}]


def test_upsert_of_foreign_row_raises_and_keeps_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    row = _row("B")
    session = FakeSession(row)
    store = _store(monkeypatch, session)
    payload = _doc(id="d1", title="x")
    before = dict(payload)
    with tenant_context("A"), pytest.raises(StoreDocumentNotFoundError) as info:
        store.save_document(payload)
    assert str(info.value) == "Document not found: d1"
    assert payload == before
    assert row.title == "t"
    assert session.added == []
    assert session.commits == 0


def test_upsert_of_own_row_updates(monkeypatch: pytest.MonkeyPatch) -> None:
    row = _row("A")
    session = FakeSession(row)
    store = _store(monkeypatch, session)
    assert store.save_document(_doc(id="d1", title="x"), tenant_id="A") == "d1"
    assert row.title == "x"
    assert session.get_kwargs == [{"with_for_update": True}]
    assert session.commits == 1


def test_insert_missing_field_raises_bare_key_error(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _store(monkeypatch, FakeSession(None))
    with pytest.raises(KeyError) as info:
        store.save_document({"id": "d1", "title": "t"})
    assert not isinstance(info.value, StoreDocumentNotFoundError)


def test_save_stale_data_maps_to_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession(_row("A"), commit_error=StaleDataError("gone"))
    store = _store(monkeypatch, session)
    with pytest.raises(StoreDocumentNotFoundError) as info:
        store.save_document(_doc(id="d1", title="x"), tenant_id="A")
    assert str(info.value) == "Document not found: d1"
    assert session.rollbacks == 1


# --- update_document ----------------------------------------------------------


def test_update_loads_with_for_update(monkeypatch: pytest.MonkeyPatch) -> None:
    row = _row("A")
    session = FakeSession(row)
    _store(monkeypatch, session).update_document("d1", {"title": "x"}, tenant_id="A")
    assert session.get_kwargs == [{"with_for_update": True}]
    assert row.title == "x"
    assert session.commits == 1


@pytest.mark.parametrize("row", [None, _row("B")], ids=["missing", "foreign"])
def test_update_missing_and_foreign_raise_same_error(
    monkeypatch: pytest.MonkeyPatch, row: LegalDocument | None
) -> None:
    session = FakeSession(row)
    store = _store(monkeypatch, session)
    with tenant_context("A"), pytest.raises(StoreDocumentNotFoundError) as info:
        store.update_document("d1", {"title": "x"})
    assert str(info.value) == "Document not found: d1"
    assert session.commits == 0
    if row is not None:
        assert row.title == "t"


def test_update_argument_wins_over_context(monkeypatch: pytest.MonkeyPatch) -> None:
    row = _row("A")
    store = _store(monkeypatch, FakeSession(row))
    with tenant_context("B"):
        store.update_document("d1", {"title": "x"}, tenant_id="A")
    assert row.title == "x"


def test_update_empty_argument_falls_back_to_context(monkeypatch: pytest.MonkeyPatch) -> None:
    shared = _row(None)
    store = _store(monkeypatch, FakeSession(shared))
    with tenant_context("A"), pytest.raises(StoreDocumentNotFoundError):
        store.update_document("d1", {"title": "x"}, tenant_id="")
    assert shared.title == "t"


def test_update_stale_data_maps_to_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession(_row("A"), commit_error=StaleDataError("gone"))
    store = _store(monkeypatch, session)
    with tenant_context("A"), pytest.raises(StoreDocumentNotFoundError) as info:
        store.update_document("d1", {"title": "x"})
    assert str(info.value) == "Document not found: d1"
    assert isinstance(info.value.__cause__, StaleDataError)
    assert session.rollbacks == 1
