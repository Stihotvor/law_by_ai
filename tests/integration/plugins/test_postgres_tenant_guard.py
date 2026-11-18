"""Integration tests: tenant write guard on ``save_document`` and ``update_document``.

QA cases from ``docs/design/tenant-write-guard/qa.md``. Rows: ``A1`` (tenant
``A``), ``B1`` (tenant ``B``), ``S1`` (shared, NULL). Needs a live PostgreSQL;
skipped when it is unreachable.
"""

from __future__ import annotations

import copy
import logging
import threading
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
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
# Seconds a test waits for another thread or for a lock waiter.
_WAIT_SECONDS = 10.0
# Distinctive payload tenant: it must never show up in a warning.
_PAYLOAD_TENANT = "tenant-secret-b7"
# Keys in a ``get_document`` dict (``mappers.doc_to_dict``).
_DOCUMENT_FIELD_COUNT = 10


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
    assert len(fetched) == _DOCUMENT_FIELD_COUNT
    return fetched


def _warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        r.getMessage() for r in caplog.records if r.name == _LOGGER and r.levelno == logging.WARNING
    ]


def _assert_not_found(exc: BaseException, doc_id: str) -> None:
    assert isinstance(exc, StoreDocumentNotFoundError)
    assert str(exc) == f"Document not found: {doc_id}"


def test_insert_takes_context_tenant_not_payload_tenant(
    store: PostgreSQLStore, caplog: pytest.LogCaptureFixture
) -> None:
    """QA-1: an insert takes the context tenant; payload ``tenant_id`` is dropped, warned."""
    caplog.set_level(logging.WARNING, logger=_LOGGER)
    with tenant_context("A"):
        doc_id = store.save_document(_payload(tenant_id=_PAYLOAD_TENANT))
    assert _snapshot(store, doc_id)["tenant_id"] == "A"
    warnings = _warnings(caplog)
    assert len(warnings) == 1
    assert "tenant_id" in warnings[0]
    assert _PAYLOAD_TENANT not in warnings[0]
    assert doc_id not in warnings[0]


def test_insert_without_tenant_is_shared(store: PostgreSQLStore) -> None:
    """QA-2: an insert with no tenant stores a shared (NULL) row."""
    with tenant_context(None):
        doc_id = store.save_document(_payload(tenant_id="B"))
    assert _snapshot(store, doc_id)["tenant_id"] is None


def test_upsert_of_foreign_id_raises_and_inserts_nothing(
    store: PostgreSQLStore, rows: dict[str, str]
) -> None:
    """QA-3: an upsert of a foreign id raises not found and writes nothing."""
    before = _snapshot(store, rows["B1"])
    with tenant_context("A"), pytest.raises(StoreDocumentNotFoundError) as info:
        store.save_document(_payload(id=rows["B1"], title="x"))
    _assert_not_found(info.value, rows["B1"])
    assert _snapshot(store, rows["B1"]) == before
    assert len(store.get_recent_changes()) == len(_TENANTS)


def test_update_of_foreign_row_raises(store: PostgreSQLStore, rows: dict[str, str]) -> None:
    """QA-4: an update of a foreign row raises not found and keeps the row."""
    before = _snapshot(store, rows["B1"])
    with tenant_context("A"), pytest.raises(StoreDocumentNotFoundError):
        store.update_document(rows["B1"], {"title": "x"})
    assert _snapshot(store, rows["B1"]) == before


def test_foreign_and_missing_ids_give_same_error(
    store: PostgreSQLStore, rows: dict[str, str]
) -> None:
    """QA-5: foreign and missing ids raise the same error type and text."""
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


def test_tenant_cannot_write_shared_row(store: PostgreSQLStore, rows: dict[str, str]) -> None:
    """QA-6: a tenant can not update or upsert a shared row."""
    before = _snapshot(store, rows["S1"])
    with tenant_context("A"):
        with pytest.raises(StoreDocumentNotFoundError):
            store.update_document(rows["S1"], {"title": "x"})
        with pytest.raises(StoreDocumentNotFoundError):
            store.save_document(_payload(id=rows["S1"], title="x"))
    assert _snapshot(store, rows["S1"]) == before


def test_no_tenant_cannot_write_tenant_row(store: PostgreSQLStore, rows: dict[str, str]) -> None:
    """QA-7: a caller with no tenant can not update a tenant row."""
    before = _snapshot(store, rows["A1"])
    with tenant_context(None), pytest.raises(StoreDocumentNotFoundError):
        store.update_document(rows["A1"], {"title": "x"})
    assert _snapshot(store, rows["A1"]) == before


def test_no_tenant_writes_shared_row(store: PostgreSQLStore, rows: dict[str, str]) -> None:
    """QA-8: a caller with no tenant can update a shared row."""
    with tenant_context(None):
        store.update_document(rows["S1"], {"title": "x"})
    after = _snapshot(store, rows["S1"])
    assert after["title"] == "x"
    assert after["tenant_id"] is None


def test_tenant_argument_wins_over_context(store: PostgreSQLStore, rows: dict[str, str]) -> None:
    """QA-9: the ``tenant_id`` argument wins over the context tenant."""
    with tenant_context("B"):
        store.update_document(rows["A1"], {"title": "x"}, tenant_id="A")
    assert _snapshot(store, rows["A1"])["title"] == "x"


def test_update_drops_payload_tenant(
    store: PostgreSQLStore, rows: dict[str, str], caplog: pytest.LogCaptureFixture
) -> None:
    """QA-10: an update drops payload ``tenant_id`` and warns without values."""
    caplog.set_level(logging.WARNING, logger=_LOGGER)
    with tenant_context("A"):
        store.update_document(rows["A1"], {"title": "x", "tenant_id": _PAYLOAD_TENANT})
    after = _snapshot(store, rows["A1"])
    assert (after["title"], after["tenant_id"]) == ("x", "A")
    warnings = _warnings(caplog)
    assert len(warnings) == 1
    assert "tenant_id" in warnings[0]
    assert _PAYLOAD_TENANT not in warnings[0]
    assert "'A'" not in warnings[0]
    assert rows["A1"] not in warnings[0]


def test_empty_tenant_argument_falls_back_to_context(
    store: PostgreSQLStore, rows: dict[str, str]
) -> None:
    """QA-11: an empty ``tenant_id`` argument falls back to the context tenant."""
    before = _snapshot(store, rows["S1"])
    with tenant_context("A"):
        with pytest.raises(StoreDocumentNotFoundError):
            store.update_document(rows["S1"], {"title": "x"}, tenant_id="")
        store.update_document(rows["A1"], {"title": "y"}, tenant_id="")
    assert _snapshot(store, rows["S1"]) == before
    assert _snapshot(store, rows["A1"])["title"] == "y"


def test_not_found_is_caught_as_key_error(store: PostgreSQLStore, rows: dict[str, str]) -> None:
    """QA-12: the not-found error is caught by ``except KeyError`` with plain text."""
    caught: KeyError | None = None
    with tenant_context("A"):
        try:
            store.update_document(rows["B1"], {"title": "x"})
        except KeyError as exc:
            caught = exc
    assert caught is not None
    assert str(caught) == f"Document not found: {rows['B1']}"
    assert isinstance(caught, LookupError)


def test_failed_upsert_keeps_row_and_payload(store: PostgreSQLStore, rows: dict[str, str]) -> None:
    """QA-13: a rejected upsert changes neither the row nor the payload."""
    before = _snapshot(store, rows["B1"])
    payload = _payload(id=rows["B1"], title="x", tenant_id="A", status="approved")
    payload_before = copy.deepcopy(payload)
    with tenant_context("A"), pytest.raises(StoreDocumentNotFoundError):
        store.save_document(payload)
    assert _snapshot(store, rows["B1"]) == before
    assert payload == payload_before


@dataclass
class _Hold:
    """Per-test state: the first commit sets *flushed*, then waits for *release*.

    *pids* holds the backend pid of each committing session, in commit order.
    """

    flushed: threading.Event = field(default_factory=threading.Event)
    release: threading.Event = field(default_factory=threading.Event)
    pids: list[int] = field(default_factory=list)


@pytest.fixture
def hold(monkeypatch: pytest.MonkeyPatch) -> _Hold:
    """Patch ``postgres.Session``: the first commit flushes, signals, then waits.

    Every commit first records its backend pid. Later commits run as usual.
    ``monkeypatch`` restores ``Session`` at teardown.
    """
    state = _Hold()

    class _HoldingSession(Session):
        def commit(self) -> None:
            state.pids.append(self.execute(text("SELECT pg_backend_pid()")).scalar_one())
            if not state.flushed.is_set():
                self.flush()
                state.flushed.set()
                assert state.release.wait(_WAIT_SECONDS)
            super().commit()

    monkeypatch.setattr(postgres, "Session", _HoldingSession)
    return state


@pytest.fixture
def other_store(store: PostgreSQLStore) -> Iterator[PostgreSQLStore]:
    """A second store (own engine) next to *store*; closed at teardown."""
    other = PostgreSQLStore()
    other.initialize()
    yield other
    other.close()


def _is_blocked_by(conn: Any, waiter: int, holder: int) -> bool:
    sql = text("SELECT CAST(:holder AS integer) = ANY(pg_blocking_pids(:waiter))")
    return bool(conn.execute(sql, {"holder": holder, "waiter": waiter}).scalar())


def _wait_until_second_blocked_by_first(hold: _Hold, timeout: float = _WAIT_SECONDS) -> None:
    """Block until the second worker's backend is blocked by the first worker's backend."""
    engine = create_engine(get_settings().postgres_url, future=True)
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            pids = list(hold.pids)
            if len(pids) >= 2:
                with engine.connect() as conn:
                    if _is_blocked_by(conn, waiter=pids[1], holder=pids[0]):
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


def _start(results: dict[str, Any], key: str, call: Any) -> threading.Thread:
    thread = threading.Thread(target=_run, args=(results, key, call))
    thread.start()
    return thread


def test_concurrent_insert_of_same_new_id_lets_one_win(
    store: PostgreSQLStore, other_store: PostgreSQLStore, hold: _Hold
) -> None:
    """QA-14: two concurrent inserts of one new id: one wins, one gets ``IntegrityError``."""
    doc_id = str(uuid.uuid4())
    results: dict[str, Any] = {}
    workers: list[threading.Thread] = []
    try:
        workers.append(_start(results, "first", lambda: store.save_document(_payload(id=doc_id))))
        assert hold.flushed.wait(_WAIT_SECONDS)
        workers.append(
            _start(results, "second", lambda: other_store.save_document(_payload(id=doc_id)))
        )
        _wait_until_second_blocked_by_first(hold)
    finally:
        hold.release.set()
        for worker in workers:
            worker.join(_WAIT_SECONDS)
        other_store.close()
    assert not any(worker.is_alive() for worker in workers)
    assert results["first"] == doc_id
    assert isinstance(results["second"], IntegrityError)


@dataclass
class _StaleCounter:
    """Per-test count of rollbacks on the stale session."""

    rollbacks: int = 0


def _stale_session(monkeypatch: pytest.MonkeyPatch) -> _StaleCounter:
    """Patch ``postgres.Session``: a flush of a changed row raises ``StaleDataError``.

    The ``monkeypatch`` fixture restores ``Session`` at teardown.
    """
    counter = _StaleCounter()

    class _StaleSession(Session):
        def flush(self, objects: Any = None) -> None:
            if self.dirty:
                raise StaleDataError("row changed under the session")
            super().flush(objects)

        def rollback(self) -> None:
            counter.rollbacks += 1
            super().rollback()

    monkeypatch.setattr(postgres, "Session", _StaleSession)
    return counter


def test_stale_data_on_commit_maps_to_not_found(
    store: PostgreSQLStore, rows: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """QA-15: ``StaleDataError`` on commit rolls back and raises not found."""
    before = _snapshot(store, rows["A1"])
    counter = _stale_session(monkeypatch)
    with tenant_context("A"), pytest.raises(StoreDocumentNotFoundError) as info:
        store.update_document(rows["A1"], {"title": "x"})
    _assert_not_found(info.value, rows["A1"])
    assert isinstance(info.value.__cause__, StaleDataError)
    assert counter.rollbacks >= 1
    assert _snapshot(store, rows["A1"]) == before
