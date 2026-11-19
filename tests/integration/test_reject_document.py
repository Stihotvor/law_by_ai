"""Reject a document: delete + audit row + deletion hook (issue #92).

Review state is global, so reject has no tenant check.

Marked ``integration``: needs a live PostgreSQL. Skipped if it is unreachable.
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Iterator

import pytest
from factories.db_probe import can_connect
from sqlalchemy import create_engine, text

from config.settings import get_settings
from core.security import (
    ADMIN,
    USER,
    PrincipalRequiredError,
    RequestPrincipal,
    principal_context,
)
from plugins.relational_db.postgres import PostgreSQLStore, StoreDocumentNotFoundError

pytestmark = pytest.mark.integration

ADMIN_EMAIL = "admin@example.com"


def _reject_as_admin(store: PostgreSQLStore, document_id: str, email: str = ADMIN_EMAIL) -> None:
    """Reject under an admin principal; the store reads the actor from it."""
    with principal_context(RequestPrincipal(email, ADMIN)):
        store.reject(document_id)


def _audit_rows(document_id: str) -> list[tuple[str, str, str]]:
    engine = create_engine(get_settings().postgres_url, future=True)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT document_id, source_url, admin FROM rejected_document "
                "WHERE document_id = :id"
            ),
            {"id": document_id},
        ).all()
    engine.dispose()
    return [(r[0], r[1], r[2]) for r in rows]


@pytest.fixture
def source_url() -> Iterator[str]:
    """Unique source URL; its audit rows are removed afterwards."""
    url = get_settings().postgres_url
    if not can_connect(url):
        pytest.skip("PostgreSQL unavailable")
    value = f"https://example.invalid/reject92/{uuid.uuid4().hex}"
    yield value
    # The app role cannot delete audit rows; clean up as the owner.
    engine = create_engine(get_settings().postgres_owner_url, future=True)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM rejected_document WHERE source_url = :u"), {"u": value})
    engine.dispose()


@pytest.fixture
def deleted_ids() -> list[str]:
    return []


@pytest.fixture
def store(deleted_ids: list[str], source_url: str) -> Iterator[PostgreSQLStore]:
    """Store whose deletion hook records the ids it is called with."""
    s = PostgreSQLStore(on_document_deleted=deleted_ids.append)
    s.initialize()
    yield s
    s.close()


def _save(store: PostgreSQLStore, source_url: str) -> str:
    return store.save_document(
        {
            "title": "Do odrzucenia",
            "content": "Treść",
            "source": "test",
            "source_url": source_url,
        }
    )


def test_reject_deletes_row_writes_audit_and_calls_hook(
    store: PostgreSQLStore, source_url: str, deleted_ids: list[str]
) -> None:
    doc_id = _save(store, source_url)

    _reject_as_admin(store, doc_id)

    assert store.get_document(doc_id) is None
    assert _audit_rows(doc_id) == [(doc_id, source_url, ADMIN_EMAIL)]
    assert deleted_ids == [doc_id]


def test_reject_without_hook_still_deletes_and_audits(source_url: str) -> None:
    s = PostgreSQLStore()
    s.initialize()
    try:
        doc_id = _save(s, source_url)
        _reject_as_admin(s, doc_id)
        assert s.get_document(doc_id) is None
        assert len(_audit_rows(doc_id)) == 1
    finally:
        s.close()


def test_reject_records_utc_timestamp(store: PostgreSQLStore, source_url: str) -> None:
    doc_id = _save(store, source_url)
    _reject_as_admin(store, doc_id)

    engine = create_engine(get_settings().postgres_url, future=True)
    with engine.connect() as conn:
        rejected_at = conn.execute(
            text("SELECT rejected_at FROM rejected_document WHERE document_id = :id"),
            {"id": doc_id},
        ).scalar_one()
    engine.dispose()
    assert rejected_at.tzinfo is not None


def test_is_rejected_true_after_reject(store: PostgreSQLStore, source_url: str) -> None:
    doc_id = _save(store, source_url)
    _reject_as_admin(store, doc_id)

    assert store.is_rejected(source_url) is True


def test_is_rejected_false_for_unknown_url(store: PostgreSQLStore, source_url: str) -> None:
    assert store.is_rejected(source_url) is False


def test_reject_unknown_id_raises_without_audit_or_hook(
    store: PostgreSQLStore, deleted_ids: list[str]
) -> None:
    missing = f"missing-{uuid.uuid4().hex}"

    with pytest.raises(StoreDocumentNotFoundError, match=missing):
        _reject_as_admin(store, missing)

    assert _audit_rows(missing) == []
    assert deleted_ids == []


class _ListHandler(logging.Handler):
    """Collect records on the store logger. Alembic's logging setup in ``initialize()``
    can detach caplog's root handler, so the test listens on the logger itself."""

    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def test_hook_error_is_logged_and_reject_still_completes(source_url: str) -> None:
    def _boom(document_id: str) -> None:
        raise RuntimeError(f"vector store down for {document_id}")

    s = PostgreSQLStore(on_document_deleted=_boom)
    s.initialize()
    handler = _ListHandler()
    store_log = logging.getLogger("plugins.relational_db.postgres")
    store_log.addHandler(handler)
    try:
        doc_id = _save(s, source_url)
        _reject_as_admin(s, doc_id)  # must not raise
        assert s.get_document(doc_id) is None
        assert len(_audit_rows(doc_id)) == 1
        assert any("on_document_deleted hook failed" in m for m in handler.messages)
    finally:
        store_log.removeHandler(handler)
        s.close()


def test_concurrent_rejects_write_one_audit_row_and_one_hook_call(
    store: PostgreSQLStore, source_url: str, deleted_ids: list[str]
) -> None:
    doc_id = _save(store, source_url)
    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def _worker() -> None:
        # A new thread does not inherit context variables: enter the principal here.
        barrier.wait()
        try:
            _reject_as_admin(store, doc_id)
            outcomes.append("ok")
        except StoreDocumentNotFoundError:
            outcomes.append("not_found")

    threads = [threading.Thread(target=_worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert sorted(outcomes) == ["not_found", "ok"]
    assert len(_audit_rows(doc_id)) == 1
    assert deleted_ids == [doc_id]


def test_qa_024_reject_twice_raises_not_found_and_one_audit_row(
    store: PostgreSQLStore, source_url: str
) -> None:
    doc_id = _save(store, source_url)
    _reject_as_admin(store, doc_id)

    with pytest.raises(StoreDocumentNotFoundError, match=doc_id):
        _reject_as_admin(store, doc_id)

    assert _audit_rows(doc_id) == [(doc_id, source_url, ADMIN_EMAIL)]


def test_qa_026_audit_insert_failure_keeps_document_and_writes_no_audit(
    store: PostgreSQLStore,
    source_url: str,
    deleted_ids: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    doc_id = _save(store, source_url)

    def _boom(**_kwargs: object) -> None:
        raise RuntimeError("audit insert forced to fail")

    monkeypatch.setattr("plugins.relational_db.postgres.RejectedDocument", _boom)

    with pytest.raises(RuntimeError, match="audit insert forced to fail"):
        _reject_as_admin(store, doc_id)

    assert store.get_document(doc_id) is not None
    assert _audit_rows(doc_id) == []
    assert deleted_ids == []


@pytest.mark.parametrize(
    "principal",
    [
        None,
        RequestPrincipal("", ADMIN),
        RequestPrincipal("   ", ADMIN),
        RequestPrincipal(ADMIN_EMAIL, USER),
    ],
    ids=["none", "blank-email", "spaces-email", "role-user"],
)
def test_reject_refused_principal_writes_nothing(
    store: PostgreSQLStore,
    source_url: str,
    deleted_ids: list[str],
    principal: RequestPrincipal | None,
) -> None:
    doc_id = _save(store, source_url)

    with principal_context(principal), pytest.raises(PrincipalRequiredError):
        store.reject(doc_id)

    assert _audit_rows(doc_id) == []
    assert store.get_document(doc_id) is not None
    assert deleted_ids == []


@pytest.mark.parametrize("email", ["boss@x.pl", "  boss@x.pl  "], ids=["plain", "padded"])
def test_reject_audit_actor_equals_principal_email(
    store: PostgreSQLStore, source_url: str, email: str
) -> None:
    doc_id = _save(store, source_url)

    _reject_as_admin(store, doc_id, email)

    assert _audit_rows(doc_id) == [(doc_id, source_url, "boss@x.pl")]
