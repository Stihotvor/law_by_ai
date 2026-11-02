from datetime import UTC, datetime
from typing import ClassVar

import pytest

from agents.fetch.contracts import (
    DocumentFilter,
    DocumentMeta,
    DocumentPage,
    DocumentRef,
    FetchedDocument,
)
from agents.fetch.document_fetcher import DocumentFetcherAgent
from agents.fetch.errors import DocumentRejectedError, SourceConfigError
from agents.fetch.registry import Registry, UnknownNameError
from agents.fetch.sources.base import LegalSource, _validate_source
from agents.fetch.strategies.base import FetchStrategy

REF = DocumentRef(source="fake", external_id="1", url="https://fake.example/1")
META = DocumentMeta(ref=REF, title="t")
PAGE = DocumentPage(items=(REF,))
DOC = FetchedDocument(meta=META, content=b"x", fetched_at=datetime(2026, 1, 1, tzinfo=UTC))


class FakeStrategy:
    built_with: ClassVar[list[str]] = []
    reads: ClassVar[list[DocumentRef]] = []

    def __init__(self, base_url: str) -> None:
        self.built_with.append(base_url)

    def list_refs(self, source: str, flt: DocumentFilter) -> DocumentPage:
        return PAGE

    def get_meta(self, ref: DocumentRef) -> DocumentMeta:
        return META

    def read(self, ref: DocumentRef) -> bytes:
        self.reads.append(ref)
        return b"x"


class FakeSource(LegalSource):
    name: ClassVar[str] = "fake"
    base_url: ClassVar[str] = "https://fake.example"
    strategy_name: ClassVar[str] = "fake_strategy"

    def list_documents(self, flt: DocumentFilter) -> DocumentPage:
        return PAGE

    def get_document_meta(self, ref: DocumentRef) -> DocumentMeta:
        return META

    def fetch_document(self, ref: DocumentRef) -> FetchedDocument:
        self.strategy.read(ref)
        return DOC


class Rejecting:
    def is_rejected(self, source_url: str) -> bool:
        return True


@pytest.fixture(autouse=True)
def registries(monkeypatch: pytest.MonkeyPatch) -> Registry[type[LegalSource]]:
    FakeStrategy.built_with.clear()
    FakeStrategy.reads.clear()
    sources: Registry[type[LegalSource]] = Registry("sources", _validate_source)
    strategies: Registry[type[FetchStrategy]] = Registry("strategies")
    sources.register("fake")(FakeSource)
    strategies.register("fake_strategy")(FakeStrategy)
    monkeypatch.setattr("agents.fetch.document_fetcher.SOURCES", sources)
    monkeypatch.setattr("agents.fetch.document_fetcher.STRATEGIES", strategies)
    return sources


def test_delegation() -> None:
    agent = DocumentFetcherAgent()
    assert agent.list_documents("fake", DocumentFilter()) == PAGE
    assert agent.get_document_meta("fake", REF) == META


def test_fetch_tenant() -> None:
    agent = DocumentFetcherAgent()
    assert agent.fetch_document("fake", REF, tenant_id="t1").tenant_id == "t1"
    assert agent.fetch_document("fake", REF).tenant_id is None


def test_unknown_source() -> None:
    with pytest.raises(UnknownNameError):
        DocumentFetcherAgent().list_documents("nope", DocumentFilter())


def test_unknown_strategy(registries: Registry[type[LegalSource]]) -> None:
    class Bad(FakeSource):
        name: ClassVar[str] = "bad"
        strategy_name: ClassVar[str] = "missing"

    registries.register("bad")(Bad)
    with pytest.raises(SourceConfigError):
        DocumentFetcherAgent().list_documents("bad", DocumentFilter())


def test_rejected() -> None:
    with pytest.raises(DocumentRejectedError):
        DocumentFetcherAgent(Rejecting()).fetch_document("fake", REF)
    assert FakeStrategy.reads == []
    assert FakeStrategy.built_with == []


def test_source_mismatch() -> None:
    agent = DocumentFetcherAgent()
    with pytest.raises(ValueError):
        agent.fetch_document("other", REF)
    with pytest.raises(ValueError):
        agent.get_document_meta("other", REF)


def test_strategy_built_with_base_url() -> None:
    DocumentFetcherAgent().list_documents("fake", DocumentFilter())
    assert FakeStrategy.built_with == ["https://fake.example"]
