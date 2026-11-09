"""The fetcher blocks documents rejected in the PostgreSQL store (issue #10).

Marked ``integration``: needs a live PostgreSQL. Skipped if it is unreachable.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import ClassVar

import pytest
from sqlalchemy import create_engine, text

from agents.fetch.contracts import (
    DocumentFilter,
    DocumentMeta,
    DocumentPage,
    DocumentRef,
    FetchedDocument,
)
from agents.fetch.document_fetcher import DocumentFetcherAgent
from agents.fetch.errors import DocumentRejectedError
from agents.fetch.registry import Registry
from agents.fetch.sources.base import LegalSource, _validate_source
from agents.fetch.strategies.base import FetchStrategy
from config.settings import get_settings
from plugins.relational_db.postgres import PostgreSQLStore

pytestmark = pytest.mark.integration

_BASE = "https://example.invalid/fetch10"


class FakeStrategy:
    reads: ClassVar[list[DocumentRef]] = []

    def __init__(self, base_url: str) -> None:
        pass

    def list_refs(self, source: str, flt: DocumentFilter) -> DocumentPage:
        return DocumentPage(items=())

    def get_meta(self, ref: DocumentRef) -> DocumentMeta:
        return DocumentMeta(ref=ref, title="t")

    def read(self, ref: DocumentRef) -> bytes:
        self.reads.append(ref)
        return b"x"


class FakeSource(LegalSource):
    name: ClassVar[str] = "fake"
    base_url: ClassVar[str] = _BASE
    strategy_name: ClassVar[str] = "fake_strategy"

    def list_documents(self, flt: DocumentFilter) -> DocumentPage:
        return self.strategy.list_refs(self.name, flt)

    def get_document_meta(self, ref: DocumentRef) -> DocumentMeta:
        return self.strategy.get_meta(ref)

    def fetch_document(self, ref: DocumentRef) -> FetchedDocument:
        content = self.strategy.read(ref)
        return FetchedDocument(
            meta=self.strategy.get_meta(ref),
            content=content,
            fetched_at=datetime(2026, 1, 1, tzinfo=UTC),
        )


def _can_connect(url: str) -> bool:
    """Return True when the database at the URL answers a query."""
    try:
        engine = create_engine(url, future=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return True
    except Exception:
        return False


@pytest.fixture(autouse=True)
def registries(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeStrategy.reads.clear()
    sources: Registry[type[LegalSource]] = Registry("sources", _validate_source)
    strategies: Registry[type[FetchStrategy]] = Registry("strategies")
    sources.register("fake")(FakeSource)
    strategies.register("fake_strategy")(FakeStrategy)
    monkeypatch.setattr("agents.fetch.document_fetcher.SOURCES", sources)
    monkeypatch.setattr("agents.fetch.document_fetcher.STRATEGIES", strategies)


@pytest.fixture
def source_url() -> Iterator[str]:
    """Unique source URL; its audit rows are removed afterwards."""
    url = get_settings().postgres_url
    if not _can_connect(url):
        pytest.skip("PostgreSQL unavailable")
    value = f"{_BASE}/{uuid.uuid4().hex}"
    yield value
    engine = create_engine(url, future=True)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM rejected_document WHERE source_url = :u"), {"u": value})
    engine.dispose()


@pytest.fixture
def store(source_url: str) -> Iterator[PostgreSQLStore]:
    s = PostgreSQLStore()
    s.initialize()
    yield s
    s.close()


def _ref(url: str) -> DocumentRef:
    return DocumentRef(source="fake", external_id=url.rsplit("/", 1)[-1], url=url)


def test_rejected_url_is_blocked_before_read(store: PostgreSQLStore, source_url: str) -> None:
    doc_id = store.save_document(
        {"title": "Do odrzucenia", "content": "Treść", "source": "test", "source_url": source_url}
    )
    store.reject(doc_id, "admin@example.com")

    with DocumentFetcherAgent(rejection=store) as agent, pytest.raises(DocumentRejectedError):
        agent.fetch_document("fake", _ref(source_url))
    assert FakeStrategy.reads == []


def test_not_rejected_url_fetches(store: PostgreSQLStore, source_url: str) -> None:
    ref = _ref(source_url)

    with DocumentFetcherAgent(rejection=store) as agent:
        result = agent.fetch_document("fake", ref)
    assert result.content == b"x"
    assert FakeStrategy.reads == [ref]
