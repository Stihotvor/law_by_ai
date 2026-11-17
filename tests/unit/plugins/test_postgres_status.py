"""Status guard in ``apply_update`` and reject errors in the PostgreSQL store.

Unit tests: ``apply_update`` works on a detached ORM row, so no PostgreSQL
instance is needed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

import plugins.relational_db.mappers as mappers_module
from data.models import Base, LegalDocument
from plugins.relational_db.mappers import apply_update
from plugins.relational_db.postgres import StoreDocumentNotFoundError


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


def test_not_found_error_is_lookup_error_not_value_error() -> None:
    assert issubclass(StoreDocumentNotFoundError, LookupError)
    assert not issubclass(StoreDocumentNotFoundError, ValueError)
