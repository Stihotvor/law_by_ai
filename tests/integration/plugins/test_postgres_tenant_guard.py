"""Integration tests: tenant write guard on ``save_document`` and ``update_document``.

QA cases from ``docs/design/tenant-write-guard/qa.md``. Rows: ``A1`` (tenant
``A``), ``B1`` (tenant ``B``), ``S1`` (shared, NULL). Needs a live PostgreSQL;
skipped when it is unreachable.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from factories.db_probe import can_connect
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from config.settings import get_settings
from core.security import tenant_context
from plugins.relational_db import postgres
from plugins.relational_db.postgres import PostgreSQLStore, StoreDocumentNotFoundError

pytestmark = pytest.mark.integration

_LOGGER = "plugins.relational_db.postgres"
_TENANTS = {"A1": "A", "B1": "B", "S1": None}


def _owner_exec(sql: str) -> None:
    engine = create_engine(get_settings().postgres_owner_url, future=True)
    try:
        with engine.begin() as conn:
            conn.execute(text(sql))
    finally:
        engine.dispose()


def _payload(**extra: Any) -> dict[str, Any]:
    return {
        "title": "Original",
        "content": "Body",
        "source": "test",
        "source_url": "https://example.invalid/",
        "metadata": {"pages": 1},
        "is_processed": False,
        **extra,
    }


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
def rows(store: PostgreSQLStore) -> dict[str, str]:
    """Insert ``A1``, ``B1`` and ``S1``; return name -> id."""
    ids: dict[str, str] = {}
    for name, tenant in _TENANTS.items():
        with tenant_context(None):
            ids[name] = store.save_document(_payload(id=str(uuid.uuid4())), tenant_id=tenant)
    return ids


def _snapshot(store: PostgreSQLStore, doc_id: str) -> dict[str, Any]:
    fetched = store.get_document(doc_id)
    assert fetched is not None
    assert len(fetched) == 10
    return fetched


def _warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        r.getMessage() for r in caplog.records if r.name == _LOGGER and r.levelno == logging.WARNING
    ]


def _assert_not_found(exc: BaseException, doc_id: str) -> None:
    assert isinstance(exc, StoreDocumentNotFoundError)
    assert str(exc) == f"Document not found: {doc_id}"


def test_qa1_insert_ignores_payload_tenant(
    store: PostgreSQLStore, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger=_LOGGER)
    with tenant_context("A"):
        doc_id = store.save_document(_payload(tenant_id="B"))
    assert _snapshot(store, doc_id)["tenant_id"] == "A"
    warnings = _warnings(caplog)
    assert len(warnings) == 1
    assert "tenant_id" in warnings[0]
    assert "'B'" not in warnings[0]


def test_qa2_insert_without_tenant_is_shared(store: PostgreSQLStore) -> None:
    with tenant_context(None):
        doc_id = store.save_document(_payload(tenant_id="B"))
    assert _snapshot(store, doc_id)["tenant_id"] is None


def test_qa3_upsert_of_foreign_id_raises_and_inserts_nothing(
    store: PostgreSQLStore, rows: dict[str, str]
) -> None:
    before = _snapshot(store, rows["B1"])
    with tenant_context("A"), pytest.raises(StoreDocumentNotFoundError) as info:
        store.save_document(_payload(id=rows["B1"], title="x"))
    _assert_not_found(info.value, rows["B1"])
    assert _snapshot(store, rows["B1"]) == before
    assert len(store.get_recent_changes()) == 3


def test_qa4_update_of_foreign_row_raises(store: PostgreSQLStore, rows: dict[str, str]) -> None:
    before = _snapshot(store, rows["B1"])
    with tenant_context("A"), pytest.raises(StoreDocumentNotFoundError):
        store.update_document(rows["B1"], {"title": "x"})
    assert _snapshot(store, rows["B1"]) == before


def test_qa5_foreign_and_missing_ids_give_same_error(
    store: PostgreSQLStore, rows: dict[str, str]
) -> None:
    missing = str(uuid.uuid4())
    errors: list[BaseException] = []
    with tenant_context("A"):
        for doc_id in (rows["B1"], missing):
            with pytest.raises(StoreDocumentNotFoundError) as info:
                store.update_document(doc_id, {"title": "x"})
            errors.append(info.value)
    assert type(errors[0]) is type(errors[1])
    _assert_not_found(errors[0], rows["B1"])
    _assert_not_found(errors[1], missing)
    assert store.get_document(missing) is None


def test_qa6_tenant_cannot_write_shared_row(store: PostgreSQLStore, rows: dict[str, str]) -> None:
    before = _snapshot(store, rows["S1"])
    with tenant_context("A"):
        with pytest.raises(StoreDocumentNotFoundError):
            store.update_document(rows["S1"], {"title": "x"})
        with pytest.raises(StoreDocumentNotFoundError):
            store.save_document(_payload(id=rows["S1"], title="x"))
    assert _snapshot(store, rows["S1"]) == before


def test_qa7_no_tenant_cannot_write_tenant_row(
    store: PostgreSQLStore, rows: dict[str, str]
) -> None:
    before = _snapshot(store, rows["A1"])
    with tenant_context(None), pytest.raises(StoreDocumentNotFoundError):
        store.update_document(rows["A1"], {"title": "x"})
    assert _snapshot(store, rows["A1"]) == before


def test_qa8_no_tenant_writes_shared_row(store: PostgreSQLStore, rows: dict[str, str]) -> None:
    with tenant_context(None):
        store.update_document(rows["S1"], {"title": "x"})
    after = _snapshot(store, rows["S1"])
    assert after["title"] == "x"
    assert after["tenant_id"] is None


def test_qa9_argument_wins_over_context(store: PostgreSQLStore, rows: dict[str, str]) -> None:
    with tenant_context("B"):
        store.update_document(rows["A1"], {"title": "x"}, tenant_id="A")
    assert _snapshot(store, rows["A1"])["title"] == "x"


def test_qa10_update_drops_payload_tenant(
    store: PostgreSQLStore, rows: dict[str, str], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger=_LOGGER)
    with tenant_context("A"):
        store.update_document(rows["A1"], {"title": "x", "tenant_id": "B"})
    after = _snapshot(store, rows["A1"])
    assert (after["title"], after["tenant_id"]) == ("x", "A")
    warnings = _warnings(caplog)
    assert len(warnings) == 1
    assert "tenant_id" in warnings[0]
    assert "'B'" not in warnings[0]
    assert "'A'" not in warnings[0]


def test_qa11_empty_argument_falls_back_to_context(
    store: PostgreSQLStore, rows: dict[str, str]
) -> None:
    before = _snapshot(store, rows["S1"])
    with tenant_context("A"):
        with pytest.raises(StoreDocumentNotFoundError):
            store.update_document(rows["S1"], {"title": "x"}, tenant_id="")
        store.update_document(rows["A1"], {"title": "y"}, tenant_id="")
    assert _snapshot(store, rows["S1"]) == before
    assert _snapshot(store, rows["A1"])["title"] == "y"


def test_qa12_not_found_is_caught_as_key_error(
    store: PostgreSQLStore, rows: dict[str, str]
) -> None:
    caught: KeyError | None = None
    with tenant_context("A"):
        try:
            store.update_document(rows["B1"], {"title": "x"})
        except KeyError as exc:
            caught = exc
    assert caught is not None
    assert str(caught) == f"Document not found: {rows['B1']}"
    assert isinstance(caught, LookupError)


def test_qa13_failed_upsert_keeps_row_and_payload(
    store: PostgreSQLStore, rows: dict[str, str]
) -> None:
    before = _snapshot(store, rows["B1"])
    payload = _payload(id=rows["B1"], title="x", tenant_id="A", status="approved")
    copy = dict(payload)
    with tenant_context("A"), pytest.raises(StoreDocumentNotFoundError):
        store.save_document(payload)
    assert _snapshot(store, rows["B1"]) == before
    assert payload == copy


class _HoldingSession(Session):
    """Session that flushes, signals, then waits before it commits."""

    flushed = threading.Event()
    release = threading.Event()

    def commit(self) -> None:
        self.flush()
        _HoldingSession.flushed.set()
        assert _HoldingSession.release.wait(10)
        super().commit()


def _wait_for_lock_waiter(timeout: float = 10.0) -> None:
    """Block until a backend waits on a lock (the second insert)."""
    engine = create_engine(get_settings().postgres_url, future=True)
    sql = text("SELECT count(*) FROM pg_stat_activity WHERE wait_event_type = 'Lock'")
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            with engine.connect() as conn:
                if conn.execute(sql).scalar():
                    return
            time.sleep(0.05)
    finally:
        engine.dispose()
    pytest.fail("second insert never waited on the first")


def _run(results: dict[str, Any], key: str, call: Any) -> None:
    try:
        results[key] = call()
    except Exception as exc:
        results[key] = exc


def test_qa14_concurrent_insert_of_same_new_id(
    store: PostgreSQLStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    doc_id = str(uuid.uuid4())
    other = PostgreSQLStore()
    other.initialize()
    _HoldingSession.flushed.clear()
    _HoldingSession.release.clear()
    monkeypatch.setattr(postgres, "Session", _HoldingSession)
    results: dict[str, Any] = {}
    first = threading.Thread(
        target=_run, args=(results, "first", lambda: store.save_document(_payload(id=doc_id)))
    )
    first.start()
    assert _HoldingSession.flushed.wait(10)
    monkeypatch.setattr(postgres, "Session", Session)
    second = threading.Thread(
        target=_run, args=(results, "second", lambda: other.save_document(_payload(id=doc_id)))
    )
    second.start()
    _wait_for_lock_waiter()
    _HoldingSession.release.set()
    first.join(10)
    second.join(10)
    other.close()
    assert results["first"] == doc_id
    assert isinstance(results["second"], IntegrityError)


class _StaleSession(Session):
    """Session whose flush of a changed row raises ``StaleDataError``."""

    rollbacks = 0

    def flush(self, objects: Any = None) -> None:
        if self.dirty:
            raise StaleDataError("row changed under the session")
        super().flush(objects)

    def rollback(self) -> None:
        _StaleSession.rollbacks += 1
        super().rollback()


def test_qa15_stale_data_maps_to_not_found(
    store: PostgreSQLStore, rows: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    before = _snapshot(store, rows["A1"])
    _StaleSession.rollbacks = 0
    monkeypatch.setattr(postgres, "Session", _StaleSession)
    with tenant_context("A"), pytest.raises(StoreDocumentNotFoundError) as info:
        store.update_document(rows["A1"], {"title": "x"})
    monkeypatch.setattr(postgres, "Session", Session)
    _assert_not_found(info.value, rows["A1"])
    assert isinstance(info.value.__cause__, StaleDataError)
    assert _StaleSession.rollbacks >= 1
    assert _snapshot(store, rows["A1"]) == before
