"""Celery task ``fetch_document`` with a real PostgreSQL store.

Wiring under test: task -> fetcher -> rejection check -> store. Only the document
source is fake; the store is a real ``PostgreSQLStore``.

Marked ``integration``: needs a live PostgreSQL. Skipped if it is unreachable.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any, ClassVar

import pytest
from sqlalchemy import create_engine, text

from agents.fetch.contracts import (
    DocumentFilter,
    DocumentMeta,
    DocumentPage,
    DocumentRef,
    FetchedDocument,
)
from agents.fetch.registry import Registry
from agents.fetch.sources.base import LegalSource, _validate_source
from agents.fetch.strategies.base import FetchStrategy
from config.settings import get_settings
from plugins.relational_db.postgres import PostgreSQLStore
from tasks import fetch
from tasks.celery_app import app

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("eager_celery")]

_BASE = "https://example.invalid/fetch11"
_SOURCE = "fake"
_TITLE = "Ustawa testowa"
_BODY = "Art. 1. Treść ustawy."
_FETCHED_AT = datetime(2026, 1, 2, tzinfo=UTC)


class FakeStrategy:
    reads: ClassVar[list[DocumentRef]] = []

    def __init__(self, base_url: str) -> None:
        pass

    def list_refs(self, source: str, flt: DocumentFilter) -> DocumentPage:
        return DocumentPage(items=())

    def make_ref(self, source: str, external_id: str) -> DocumentRef:
        return DocumentRef(source=source, external_id=external_id, url=f"{_BASE}/{external_id}")

    def get_meta(self, ref: DocumentRef) -> DocumentMeta:
        return DocumentMeta(ref=ref, title=_TITLE, extra={"k": "v"})

    def read(self, ref: DocumentRef) -> bytes:
        self.reads.append(ref)
        return _BODY.encode("utf-8")


class FakeSource(LegalSource):
    name: ClassVar[str] = _SOURCE
    base_url: ClassVar[str] = _BASE
    strategy_name: ClassVar[str] = "fake_strategy"

    def list_documents(self, flt: DocumentFilter) -> DocumentPage:
        return self.strategy.list_refs(self.name, flt)

    def get_document_meta(self, ref: DocumentRef) -> DocumentMeta:
        return self.strategy.get_meta(ref)

    def fetch_document(self, ref: DocumentRef) -> FetchedDocument:
        return FetchedDocument(
            meta=self.strategy.get_meta(ref),
            content=self.strategy.read(ref),
            content_type="text/plain; charset=utf-8",
            fetched_at=_FETCHED_AT,
        )


def _rows(source_url: str) -> list[dict[str, Any]]:
    """Return the ``legal_document`` rows with *source_url*, read with plain SQL."""
    engine = create_engine(get_settings().postgres_url, future=True)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, source_url, source, title, content, status, tenant_id "
                "FROM legal_document WHERE source_url = :u"
            ),
            {"u": source_url},
        ).all()
    engine.dispose()
    return [dict(r._mapping) for r in rows]


@pytest.fixture(autouse=True)
def registries(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeStrategy.reads.clear()
    sources: Registry[type[LegalSource]] = Registry("sources", _validate_source)
    strategies: Registry[type[FetchStrategy]] = Registry("strategies")
    sources.register(_SOURCE)(FakeSource)
    strategies.register("fake_strategy")(FakeStrategy)
    monkeypatch.setattr("agents.fetch.document_fetcher.SOURCES", sources)
    monkeypatch.setattr("agents.fetch.document_fetcher.STRATEGIES", strategies)


@pytest.fixture
def source_url(postgres_url: str) -> Iterator[str]:
    """Unique source URL; its document and audit rows are removed afterwards."""
    value = f"{_BASE}/{uuid.uuid4().hex}.txt"
    yield value
    engine = create_engine(postgres_url, future=True)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM legal_document WHERE source_url = :u"), {"u": value})
        conn.execute(text("DELETE FROM rejected_document WHERE source_url = :u"), {"u": value})
    engine.dispose()


@pytest.fixture
def store(source_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgreSQLStore]:
    """Real store that the task gets from ``_make_store``."""
    s = PostgreSQLStore()
    s.initialize()
    original = fetch._make_store
    original.cache_clear()
    monkeypatch.setattr(fetch, "_make_store", lambda: s)
    try:
        yield s
    finally:
        try:
            s.close()
        finally:
            original.cache_clear()


def _run(source_url: str, tenant_id: str | None = None) -> Any:
    external_id = source_url.removeprefix(f"{_BASE}/")
    return app.tasks["fetch_document"].delay(_SOURCE, external_id, tenant_id=tenant_id).get()


def test_task_saves_fetched_document(store: PostgreSQLStore, source_url: str) -> None:
    result = _run(source_url, tenant_id="tenant-a")

    assert result["status"] == "saved"
    assert result["source_url"] == source_url
    rows = _rows(source_url)
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == result["document_id"]
    assert row["source_url"] == source_url
    assert row["source"] == _SOURCE
    assert row["title"] == _TITLE
    assert row["content"] == _BODY
    assert row["status"] == "needs_review"
    assert row["tenant_id"] == "tenant-a"


def test_task_skips_rejected_url(store: PostgreSQLStore, source_url: str) -> None:
    doc_id = store.save_document(
        {"title": "Do odrzucenia", "content": "Treść", "source": "test", "source_url": source_url}
    )
    store.reject(doc_id, "admin@example.com")

    result = _run(source_url)

    assert result == {"status": "skipped", "source_url": source_url}
    assert _rows(source_url) == []
    assert FakeStrategy.reads == []


def test_task_without_tenant_saves_shared_document(store: PostgreSQLStore, source_url: str) -> None:
    result = _run(source_url, tenant_id=None)

    assert result["status"] == "saved"
    rows = _rows(source_url)
    assert len(rows) == 1
    assert rows[0]["tenant_id"] is None
