"""Status guard in ``apply_update`` and reject errors in the PostgreSQL store.

Unit tests: ``apply_update`` works on a detached ORM row and the store tests
use a fake ``Session``, so no PostgreSQL instance is needed.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import pytest

import plugins.relational_db.mappers as mappers_module
from data.models import Base, LegalDocument
from plugins.relational_db import postgres
from plugins.relational_db.mappers import apply_update
from plugins.relational_db.postgres import PostgreSQLStore, StoreDocumentNotFoundError


def _row(**overrides: Any) -> LegalDocument:
    fields: dict[str, Any] = {
        "id": "d1",
        "title": "t",
        "content": "c",
        "source": "s",
        "source_url": "u",
        "is_processed": False,
        "tenant_id": "t1",
        "status": "needs_review",
    }
    return LegalDocument(**{**fields, **overrides})


def test_apply_update_drops_status() -> None:
    row = _row()
    dropped = apply_update(row, {"status": "approved", "title": "x"})
    assert row.status == "needs_review"
    assert row.title == "x"
    assert dropped == ["status"]


@pytest.mark.parametrize("value", ["approved", "bogus", "rejected", "", None])
def test_apply_update_drops_any_status_value(value: object) -> None:
    row = _row()
    dropped = apply_update(row, {"status": value})
    assert row.status == "needs_review"
    assert dropped == ["status"]


def test_apply_update_drops_tenant_id_and_unknown_keys() -> None:
    row = _row()
    dropped = apply_update(row, {"tenant_id": "t2", "foo": 1})
    assert row.tenant_id == "t1"
    assert dropped == ["foo", "tenant_id"]


def test_apply_update_ignores_id_without_reporting_it() -> None:
    row = _row()
    dropped = apply_update(row, {"id": "d2"})
    assert row.id == "d1"
    assert dropped == []


def test_apply_update_copies_allowed_keys() -> None:
    row = _row()
    when = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    meta = {"k": "v"}
    dropped = apply_update(
        row,
        {
            "title": "T2",
            "content": "C2",
            "source": "S2",
            "source_url": "U2",
            "is_processed": True,
            "metadata": meta,
            "last_updated": "2026-01-02T03:04:05Z",
        },
    )
    assert (row.title, row.content, row.source, row.source_url) == ("T2", "C2", "S2", "U2")
    assert row.is_processed is True
    assert row.last_updated == when
    assert row.metadata_ == meta
    # A raw setattr of "metadata" would shadow the declarative Base.metadata.
    assert row.metadata is Base.metadata
    assert dropped == []


def test_apply_update_does_not_mutate_input() -> None:
    payload: dict[str, Any] = {"status": "approved", "title": "x"}
    before = dict(payload)
    apply_update(_row(), payload)
    assert payload == before


def test_validate_status_is_removed() -> None:
    assert not hasattr(mappers_module, "validate_status")


def test_not_found_error_is_key_error_not_value_error() -> None:
    assert issubclass(StoreDocumentNotFoundError, KeyError)
    assert issubclass(StoreDocumentNotFoundError, LookupError)
    assert not issubclass(StoreDocumentNotFoundError, ValueError)


class FakeSession:
    """Fake session: ``get`` returns *row* (or ``None``); ``add`` records rows."""

    def __init__(self, row: LegalDocument | None) -> None:
        self.row = row
        self.added: list[Any] = []

    def __enter__(self) -> FakeSession:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def get(self, _model: object, _key: str, **_kwargs: object) -> LegalDocument | None:
        return self.row

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    def commit(self) -> None:
        return None


def _store(
    monkeypatch: pytest.MonkeyPatch, row: LegalDocument | None
) -> tuple[PostgreSQLStore, FakeSession]:
    session = FakeSession(row)
    store = PostgreSQLStore()
    monkeypatch.setattr(store, "_ensure_initialized", lambda: None)
    monkeypatch.setattr(postgres, "Session", lambda _engine: session)
    return store, session


def _doc(**extra: Any) -> dict[str, Any]:
    return {"id": "d1", "title": "t", "content": "c", "source": "s", "source_url": "u", **extra}


def _warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]


def test_save_insert_with_status_stores_needs_review_and_warns(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    store, session = _store(monkeypatch, None)
    with caplog.at_level(logging.WARNING, logger=postgres.__name__):
        store.save_document(_doc(status="approved"), tenant_id="t1")
    assert len(session.added) == 1
    assert session.added[0].status == "needs_review"
    messages = _warnings(caplog)
    assert len(messages) == 1
    assert "status" in messages[0]
    assert "approved" not in messages[0]


def test_save_insert_without_status_does_not_warn(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    store, session = _store(monkeypatch, None)
    with caplog.at_level(logging.WARNING, logger=postgres.__name__):
        store.save_document(_doc(), tenant_id="t1")
    assert len(session.added) == 1
    assert session.added[0].status == "needs_review"
    assert _warnings(caplog) == []


def test_update_document_drops_status_and_warns(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    row = _row()
    store, _ = _store(monkeypatch, row)
    with caplog.at_level(logging.WARNING, logger=postgres.__name__):
        store.update_document("d1", {"status": "approved", "title": "x"}, tenant_id="t1")
    assert row.status == "needs_review"
    assert row.title == "x"
    messages = _warnings(caplog)
    assert len(messages) == 1
    assert "status" in messages[0]
    assert "approved" not in messages[0]


def test_update_document_missing_row_raises_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    store, _ = _store(monkeypatch, None)
    with pytest.raises(StoreDocumentNotFoundError, match=r"^Document not found: missing$"):
        store.update_document("missing", {"title": "x"})
