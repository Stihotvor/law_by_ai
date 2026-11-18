"""Tenant guard on the document calls of ``PostgreSQLStore`` (unit level).

Write guard: ``save_document`` and ``update_document``. Read and delete guard:
``get_document``, ``search_documents``, ``get_recent_changes`` and
``delete_document`` (``docs/design/tenant-read-guard``).

A fake ``Session`` stands in for PostgreSQL. The integration twin in
``tests/integration/plugins/test_postgres_tenant_guard.py`` runs the QA cases
on a live database.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from fakes.postgres_session import FakeSession, make_doc, make_store, store_warnings
from sqlalchemy.orm.exc import StaleDataError

from core.security import tenant_context
from data.models import LegalDocument
from plugins.relational_db import postgres
from plugins.relational_db.postgres import (
    StoreDocumentNotFoundError,
    _require_writable,
    _resolve_tenant,
)

# Distinctive payload tenant: it must never show up in a warning.
_PAYLOAD_TENANT = "tenant-secret-b7"


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


# --- save_document ------------------------------------------------------------


def test_insert_uses_context_tenant_and_drops_payload_tenant(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    session = FakeSession(None)
    store = make_store(monkeypatch, session)
    with tenant_context("A"), caplog.at_level(logging.WARNING, logger=postgres.__name__):
        store.save_document(make_doc(id="doc-id-q4", tenant_id=_PAYLOAD_TENANT, status="approved"))
    assert session.added[0].tenant_id == "A"
    messages = store_warnings(caplog)
    assert len(messages) == 1
    assert "tenant_id" in messages[0]
    assert "status" in messages[0]
    assert _PAYLOAD_TENANT not in messages[0]
    assert "approved" not in messages[0]
    assert "doc-id-q4" not in messages[0]


def test_insert_without_tenant_is_shared(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession(None)
    store = make_store(monkeypatch, session)
    with tenant_context(None):
        store.save_document(make_doc(tenant_id="B"))
    assert session.added[0].tenant_id is None


def test_insert_loads_with_for_update(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession(None)
    make_store(monkeypatch, session).save_document(make_doc(id="d1"))
    assert session.get_kwargs == [{"with_for_update": True}]


def test_upsert_of_foreign_row_raises_and_keeps_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    row = _row("B")
    session = FakeSession(row)
    store = make_store(monkeypatch, session)
    payload = make_doc(id="d1", title="x")
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
    store = make_store(monkeypatch, session)
    assert store.save_document(make_doc(id="d1", title="x"), tenant_id="A") == "d1"
    assert row.title == "x"
    assert session.get_kwargs == [{"with_for_update": True}]
    assert session.commits == 1


def test_insert_missing_field_raises_bare_key_error(monkeypatch: pytest.MonkeyPatch) -> None:
    store = make_store(monkeypatch, FakeSession(None))
    with pytest.raises(KeyError) as info:
        store.save_document({"id": "d1", "title": "t"})
    assert not isinstance(info.value, StoreDocumentNotFoundError)


def test_save_stale_data_maps_to_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession(_row("A"), commit_error=StaleDataError("gone"))
    store = make_store(monkeypatch, session)
    with pytest.raises(StoreDocumentNotFoundError) as info:
        store.save_document(make_doc(id="d1", title="x"), tenant_id="A")
    assert str(info.value) == "Document not found: d1"
    assert session.rollbacks == 1


# --- update_document ----------------------------------------------------------


def test_update_locks_only_row_of_caller_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    row = _row("A")
    session = FakeSession(row)
    make_store(monkeypatch, session).update_document("d1", {"title": "x"}, tenant_id="A")
    assert session.get_kwargs == []
    assert len(session.statements) == 1
    sql = session.statements[0]
    assert "legal_document.id = " in sql
    assert "legal_document.tenant_id IS NOT DISTINCT FROM " in sql
    assert sql.rstrip().endswith("FOR UPDATE")
    assert row.title == "x"
    assert session.commits == 1


def test_update_of_shared_row_without_tenant_matches_null(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = _row(None)
    session = FakeSession(row)
    with tenant_context(None):
        make_store(monkeypatch, session).update_document("d1", {"title": "x"})
    assert "tenant_id IS NOT DISTINCT FROM NULL" in session.statements[0]
    assert row.title == "x"


def test_update_warning_names_keys_only(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    row = _row("A", id="doc-id-q4")
    store = make_store(monkeypatch, FakeSession(row))
    with caplog.at_level(logging.WARNING, logger=postgres.__name__):
        store.update_document(
            "doc-id-q4", {"title": "x", "tenant_id": _PAYLOAD_TENANT}, tenant_id="A"
        )
    messages = store_warnings(caplog)
    assert len(messages) == 1
    assert "update_document" in messages[0]
    assert "tenant_id" in messages[0]
    assert _PAYLOAD_TENANT not in messages[0]
    assert "doc-id-q4" not in messages[0]


@pytest.mark.parametrize("row", [None, _row("B")], ids=["missing", "foreign"])
def test_update_missing_and_foreign_raise_same_error(
    monkeypatch: pytest.MonkeyPatch, row: LegalDocument | None
) -> None:
    session = FakeSession(row)
    store = make_store(monkeypatch, session)
    with tenant_context("A"), pytest.raises(StoreDocumentNotFoundError) as info:
        store.update_document("d1", {"title": "x"})
    assert str(info.value) == "Document not found: d1"
    assert session.commits == 0
    if row is not None:
        assert row.title == "t"


def test_update_argument_wins_over_context(monkeypatch: pytest.MonkeyPatch) -> None:
    row = _row("A")
    store = make_store(monkeypatch, FakeSession(row))
    with tenant_context("B"):
        store.update_document("d1", {"title": "x"}, tenant_id="A")
    assert row.title == "x"


def test_update_empty_argument_falls_back_to_context(monkeypatch: pytest.MonkeyPatch) -> None:
    shared = _row(None)
    store = make_store(monkeypatch, FakeSession(shared))
    with tenant_context("A"), pytest.raises(StoreDocumentNotFoundError):
        store.update_document("d1", {"title": "x"}, tenant_id="")
    assert shared.title == "t"


def test_update_stale_data_maps_to_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession(_row("A"), commit_error=StaleDataError("gone"))
    store = make_store(monkeypatch, session)
    with tenant_context("A"), pytest.raises(StoreDocumentNotFoundError) as info:
        store.update_document("d1", {"title": "x"})
    assert str(info.value) == "Document not found: d1"
    assert isinstance(info.value.__cause__, StaleDataError)
    assert session.rollbacks == 1


# --- read guard: get_document, search_documents, get_recent_changes ----------

_READABLE_BY_TENANT = (
    "legal_document.tenant_id = %(tenant_id_1)s::VARCHAR OR legal_document.tenant_id IS NULL"
)
_READS: dict[str, Callable[[postgres.PostgreSQLStore, str | None], object]] = {
    "get_document": lambda s, t: s.get_document("d1", tenant_id=t),
    "search_documents": lambda s, t: s.search_documents("q", tenant_id=t),
    "get_recent_changes": lambda s, t: s.get_recent_changes(tenant_id=t),
}


def _read_sql(
    monkeypatch: pytest.MonkeyPatch, call: str, arg: str | None, context: str | None
) -> tuple[str, dict[str, Any]]:
    """Run read *call* once; return its only SQL statement and its params."""
    session = FakeSession(None)
    store = make_store(monkeypatch, session)
    with tenant_context(context):
        _READS[call](store, arg)
    assert session.get_kwargs == []
    assert len(session.statements) == 1
    return session.statements[0], session.params[0]


@pytest.mark.parametrize("call", list(_READS))
@pytest.mark.parametrize(
    ("arg", "context"),
    [("A", None), (None, "A"), ("A", "B"), ("", "A")],
    ids=["argument", "context", "argument-wins", "empty-argument-uses-context"],
)
def test_read_with_tenant_sends_own_or_shared(
    monkeypatch: pytest.MonkeyPatch, call: str, arg: str | None, context: str | None
) -> None:
    sql, params = _read_sql(monkeypatch, call, arg, context)
    assert _READABLE_BY_TENANT in sql
    assert params["tenant_id_1"] == "A"
    assert "IS NOT DISTINCT FROM" not in sql


@pytest.mark.parametrize("call", list(_READS))
@pytest.mark.parametrize(("arg", "context"), [(None, None), ("", None), ("", "")])
def test_read_without_tenant_sends_shared_only(
    monkeypatch: pytest.MonkeyPatch, call: str, arg: str | None, context: str | None
) -> None:
    sql, params = _read_sql(monkeypatch, call, arg, context)
    assert "legal_document.tenant_id IS NULL" in sql
    assert "legal_document.tenant_id = " not in sql
    assert "OR legal_document.tenant_id" not in sql
    assert "tenant_id_1" not in params
    assert "IS NOT DISTINCT FROM" not in sql


def test_search_filters_tenant_before_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    sql, params = _read_sql(monkeypatch, "search_documents", "A", None)
    assert sql.index(_READABLE_BY_TENANT) < sql.index("LIMIT")
    assert "ILIKE" in sql
    assert params["param_1"] == 10


def test_recent_changes_keeps_since_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession(None)
    make_store(monkeypatch, session).get_recent_changes(
        since="2025-01-01T00:00:00+00:00", tenant_id="A"
    )
    sql = session.statements[0]
    assert _READABLE_BY_TENANT in sql
    assert "legal_document.last_updated > " in sql


@pytest.mark.parametrize(
    ("row_tenant", "caller", "found"),
    [
        ("A", "A", True),
        (None, None, True),
        (None, "A", True),
        ("B", "A", False),
        ("A", None, False),
    ],
    ids=["own", "shared-no-tenant", "shared-tenant", "foreign", "tenant-row-no-tenant"],
)
def test_list_reads_return_readable_rows(
    monkeypatch: pytest.MonkeyPatch, row_tenant: str | None, caller: str | None, found: bool
) -> None:
    row = _row(row_tenant, last_updated=datetime(2025, 1, 1, tzinfo=UTC))
    store = make_store(monkeypatch, FakeSession(row))
    expected = ["d1"] if found else []
    assert [d["id"] for d in store.search_documents("c", tenant_id=caller)] == expected
    assert [d["id"] for d in store.get_recent_changes(tenant_id=caller)] == expected


@pytest.mark.parametrize(
    ("row_tenant", "caller", "found"),
    [
        ("A", "A", True),
        (None, None, True),
        (None, "A", True),
        ("B", "A", False),
        ("A", None, False),
    ],
    ids=["own", "shared-no-tenant", "shared-tenant", "foreign", "tenant-row-no-tenant"],
)
def test_get_document_returns_dict_or_none(
    monkeypatch: pytest.MonkeyPatch, row_tenant: str | None, caller: str | None, found: bool
) -> None:
    row = _row(row_tenant, last_updated=datetime(2025, 1, 1, tzinfo=UTC))
    store = make_store(monkeypatch, FakeSession(row))
    result = store.get_document("d1", tenant_id=caller)
    assert (result is not None) is found
    if result is not None:
        assert result["id"] == "d1"


# --- delete guard: delete_document --------------------------------------------


def _delete(monkeypatch: pytest.MonkeyPatch, arg: str | None, context: str | None) -> FakeSession:
    session = FakeSession(_row("A"))
    store = make_store(monkeypatch, session)
    with tenant_context(context):
        assert store.delete_document("d1", tenant_id=arg) is None
    return session


@pytest.mark.parametrize(
    ("arg", "context"),
    [("A", None), (None, "A"), ("A", "B"), ("", "A")],
    ids=["argument", "context", "argument-wins", "empty-argument-uses-context"],
)
def test_delete_sends_one_owned_delete_and_commits_once(
    monkeypatch: pytest.MonkeyPatch, arg: str | None, context: str | None
) -> None:
    session = _delete(monkeypatch, arg, context)
    assert session.get_kwargs == []
    assert len(session.statements) == 1
    sql = session.statements[0]
    assert sql.startswith("DELETE FROM legal_document")
    assert "legal_document.id = %(id_1)s" in sql
    assert "legal_document.tenant_id IS NOT DISTINCT FROM %(tenant_id_1)s" in sql
    assert session.params[0] == {"id_1": "d1", "tenant_id_1": "A"}
    assert session.commits == 1


def test_delete_without_tenant_matches_shared_only(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _delete(monkeypatch, "", None)
    assert "legal_document.tenant_id IS NOT DISTINCT FROM NULL" in session.statements[0]
    assert session.commits == 1
