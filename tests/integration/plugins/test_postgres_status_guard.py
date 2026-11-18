"""Integration tests: the store ignores ``status`` on save and update.

``save_document`` inserts with ``needs_review`` and the upsert and update paths
never change ``status``. Each call logs one warning with the dropped key names,
never their values. Needs a live PostgreSQL; skipped when it is unreachable.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from factories.db_probe import can_connect
from sqlalchemy import create_engine, text

from config.settings import get_settings
from plugins.relational_db.postgres import PostgreSQLStore, StoreDocumentNotFoundError

pytestmark = pytest.mark.integration

_LOGGER = "plugins.relational_db.postgres"
DocFactory = Callable[..., dict[str, Any]]


@pytest.fixture
def store() -> Iterator[PostgreSQLStore]:
    """Fresh store as the app role; the owner empties ``legal_document``."""
    if not can_connect(get_settings().postgres_url):
        pytest.skip("PostgreSQL unavailable")
    _owner_exec("TRUNCATE legal_document")
    s = PostgreSQLStore()
    s.initialize()
    yield s
    s.close()


@pytest.fixture
def make_document() -> DocFactory:
    """Factory for a minimal document dict without an id."""

    def _factory(**overrides: Any) -> dict[str, Any]:
        base: dict[str, Any] = {
            "title": "Untitled",
            "content": "Body",
            "source": "test",
            "source_url": "https://example.invalid/",
            "metadata": {"pages": 1},
            "is_processed": False,
        }
        return {**base, **overrides}

    return _factory


def _owner_exec(sql: str, **params: Any) -> None:
    """Run *sql* as the owner (the app role cannot set status or truncate)."""
    engine = create_engine(get_settings().postgres_owner_url, future=True)
    try:
        with engine.begin() as conn:
            conn.execute(text(sql), params)
    finally:
        engine.dispose()


def _set_status(doc_id: str, status: str) -> None:
    _owner_exec("UPDATE legal_document SET status = :s WHERE id = :i", s=status, i=doc_id)


def _stored_status(store: PostgreSQLStore, doc_id: str) -> str:
    fetched = store.get_document(doc_id)
    assert fetched is not None
    return fetched["status"]


def _warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        r.getMessage() for r in caplog.records if r.name == _LOGGER and r.levelno == logging.WARNING
    ]


def test_update_cannot_change_status(store: PostgreSQLStore, make_document: DocFactory) -> None:
    doc_id = store.save_document(make_document())

    store.update_document(doc_id, {"status": "approved", "title": "x"})

    fetched = store.get_document(doc_id)
    assert fetched is not None
    assert fetched["status"] == "needs_review"
    assert fetched["title"] == "x"


def test_insert_ignores_status(
    store: PostgreSQLStore, make_document: DocFactory, caplog: pytest.LogCaptureFixture
) -> None:
    doc = make_document(id=str(uuid.uuid4()), status="approved")
    assert store.get_document(doc["id"]) is None
    caplog.set_level(logging.WARNING, logger=_LOGGER)

    doc_id = store.save_document(doc)

    assert _stored_status(store, doc_id) == "needs_review"
    warnings = _warnings(caplog)
    assert len(warnings) == 1
    assert "status" in warnings[0]
    assert "approved" not in warnings[0]


def test_insert_without_status_logs_no_warning(
    store: PostgreSQLStore, make_document: DocFactory, caplog: pytest.LogCaptureFixture
) -> None:
    doc = make_document()
    caplog.set_level(logging.WARNING, logger=_LOGGER)

    doc_id = store.save_document(doc)

    assert _stored_status(store, doc_id) == "needs_review"
    assert not [w for w in _warnings(caplog) if "status" in w]
    assert set(doc) == set(make_document()) | {"id"}


@pytest.mark.parametrize("value", ["needs_review", "approved"])
def test_upsert_keeps_stored_status(
    store: PostgreSQLStore, make_document: DocFactory, value: str
) -> None:
    doc = make_document()
    doc_id = store.save_document(doc)
    _set_status(doc_id, "approved")

    store.save_document({**doc, "status": value})

    assert _stored_status(store, doc_id) == "approved"


@pytest.mark.parametrize("value", ["bogus", "rejected", "", None])
def test_unknown_status_does_not_raise(
    store: PostgreSQLStore, make_document: DocFactory, value: str | None
) -> None:
    doc_id = store.save_document(make_document())

    store.update_document(doc_id, {"status": value})

    assert _stored_status(store, doc_id) == "needs_review"


def test_warning_names_keys_not_values(
    store: PostgreSQLStore, make_document: DocFactory, caplog: pytest.LogCaptureFixture
) -> None:
    doc_id = store.save_document(make_document())
    caplog.set_level(logging.WARNING, logger=_LOGGER)

    store.update_document(doc_id, {"status": "approved-secret", "foo": 1})

    warnings = _warnings(caplog)
    assert len(warnings) == 1
    assert "status" in warnings[0]
    assert "foo" in warnings[0]
    assert "approved-secret" not in warnings[0]


def test_reads_still_return_status(store: PostgreSQLStore, make_document: DocFactory) -> None:
    doc_id = store.save_document(make_document())

    fetched = store.get_document(doc_id)

    assert fetched is not None
    assert fetched["status"] == "needs_review"


def test_upsert_cannot_approve_needs_review_row(
    store: PostgreSQLStore, make_document: DocFactory
) -> None:
    doc = make_document()
    doc_id = store.save_document(doc)

    store.save_document({**doc, "status": "approved"})

    assert _stored_status(store, doc_id) == "needs_review"


def test_insert_with_bogus_status_stores_needs_review(
    store: PostgreSQLStore, make_document: DocFactory
) -> None:
    doc_id = store.save_document(make_document(status="bogus"))

    assert _stored_status(store, doc_id) == "needs_review"


def test_upsert_warning_names_status(
    store: PostgreSQLStore, make_document: DocFactory, caplog: pytest.LogCaptureFixture
) -> None:
    doc = make_document()
    store.save_document(doc)
    caplog.set_level(logging.WARNING, logger=_LOGGER)

    store.save_document({**doc, "status": "approved"})

    warnings = _warnings(caplog)
    assert len(warnings) == 1
    assert "status" in warnings[0]
    assert "approved" not in warnings[0]


def test_title_only_update_logs_no_warning(
    store: PostgreSQLStore, make_document: DocFactory, caplog: pytest.LogCaptureFixture
) -> None:
    doc_id = store.save_document(make_document())
    caplog.set_level(logging.WARNING, logger=_LOGGER)

    store.update_document(doc_id, {"title": "only title"})

    assert _warnings(caplog) == []


def test_update_keeps_tenant_and_warns(
    store: PostgreSQLStore, make_document: DocFactory, caplog: pytest.LogCaptureFixture
) -> None:
    doc_id = store.save_document(make_document(), tenant_id="tenant-7")
    caplog.set_level(logging.WARNING, logger=_LOGGER)

    store.update_document(doc_id, {"tenant_id": "tenant-other"}, tenant_id="tenant-7")

    fetched = store.get_document(doc_id)
    assert fetched is not None
    assert fetched["tenant_id"] == "tenant-7"
    warnings = _warnings(caplog)
    assert len(warnings) == 1
    assert "tenant_id" in warnings[0]
    assert "tenant-other" not in warnings[0]


def test_upsert_keeps_tenant(store: PostgreSQLStore, make_document: DocFactory) -> None:
    doc = make_document()
    doc_id = store.save_document(doc, tenant_id="tenant-7")

    store.save_document({**doc, "tenant_id": "tenant-other"}, tenant_id="tenant-7")

    fetched = store.get_document(doc_id)
    assert fetched is not None
    assert fetched["tenant_id"] == "tenant-7"


def test_update_keeps_row_id(store: PostgreSQLStore, make_document: DocFactory) -> None:
    doc_id = store.save_document(make_document())
    other_id = str(uuid.uuid4())

    store.update_document(doc_id, {"id": other_id, "title": "moved?"})

    fetched = store.get_document(doc_id)
    assert fetched is not None
    assert fetched["id"] == doc_id
    assert fetched["title"] == "moved?"
    assert store.get_document(other_id) is None


def test_update_metadata_round_trips(store: PostgreSQLStore, make_document: DocFactory) -> None:
    doc_id = store.save_document(make_document())

    store.update_document(doc_id, {"metadata": {"pages": 9, "lang": "uk"}})

    fetched = store.get_document(doc_id)
    assert fetched is not None
    assert fetched["metadata"] == {"pages": 9, "lang": "uk"}


def test_save_without_id_ignores_approved_status(
    store: PostgreSQLStore, make_document: DocFactory
) -> None:
    doc = make_document(status="approved")
    assert "id" not in doc

    doc_id = store.save_document(doc)

    assert _stored_status(store, doc_id) == "needs_review"


def test_update_missing_id_raises_and_creates_no_row(store: PostgreSQLStore) -> None:
    missing_id = str(uuid.uuid4())

    with pytest.raises(StoreDocumentNotFoundError):
        store.update_document(missing_id, {"status": "approved"})

    assert store.get_document(missing_id) is None


def test_each_update_with_status_logs_one_warning(
    store: PostgreSQLStore, make_document: DocFactory, caplog: pytest.LogCaptureFixture
) -> None:
    doc_id = store.save_document(make_document())
    caplog.set_level(logging.WARNING, logger=_LOGGER)

    for _ in range(3):
        store.update_document(doc_id, {"status": "approved"})

    warnings = _warnings(caplog)
    assert len(warnings) == 3
    assert all("status" in w for w in warnings)
