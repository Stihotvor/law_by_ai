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
from agents.fetch.errors import DocumentRejectedError, SourceConfigError, UnknownSourceError
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


class RecordingSource(FakeSource):
    name: ClassVar[str] = "rec"
    calls: ClassVar[list[tuple[str, object]]] = []

    def list_documents(self, flt: DocumentFilter) -> DocumentPage:
        self.calls.append(("list", flt))
        return PAGE

    def get_document_meta(self, ref: DocumentRef) -> DocumentMeta:
        self.calls.append(("meta", ref))
        return META

    def fetch_document(self, ref: DocumentRef) -> FetchedDocument:
        self.calls.append(("fetch", ref))
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
    with pytest.raises(UnknownSourceError) as info:
        DocumentFetcherAgent().list_documents("nope", DocumentFilter())
    assert isinstance(info.value.__cause__, UnknownNameError)
    assert str(info.value) == "unknown source 'nope'"


def test_unknown_source_name_truncated() -> None:
    with pytest.raises(UnknownSourceError) as info:
        DocumentFetcherAgent().list_documents("x" * 200, DocumentFilter())
    assert str(info.value) == f"unknown source {'x' * 64!r}"


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


def test_arguments_forwarded(registries: Registry[type[LegalSource]]) -> None:
    registries.register("rec")(RecordingSource)
    RecordingSource.calls.clear()
    ref = REF.model_copy(update={"source": "rec"})
    flt = DocumentFilter(limit=7)
    agent = DocumentFetcherAgent()
    agent.list_documents("rec", flt)
    agent.get_document_meta("rec", ref)
    agent.fetch_document("rec", ref)
    assert RecordingSource.calls == [("list", flt), ("meta", ref), ("fetch", ref)]


def test_rejection_checker_receives_url() -> None:
    seen: list[str] = []

    class Spy:
        def is_rejected(self, source_url: str) -> bool:
            seen.append(source_url)
            return False

    DocumentFetcherAgent(Spy()).fetch_document("fake", REF)
    assert seen == [REF.url]


def test_error_messages() -> None:
    with pytest.raises(DocumentRejectedError) as rej:
        DocumentFetcherAgent(Rejecting()).fetch_document("fake", REF)
    assert str(rej.value) == "document rejected: fake/1"
    assert REF.url not in str(rej.value)
    with pytest.raises(ValueError) as mismatch:
        DocumentFetcherAgent().get_document_meta("other", REF)
    assert str(mismatch.value) == "ref.source 'fake' does not match source 'other'"


def test_unknown_strategy_message(registries: Registry[type[LegalSource]]) -> None:
    class Bad(FakeSource):
        name: ClassVar[str] = "bad"
        strategy_name: ClassVar[str] = "missing"

    registries.register("bad")(Bad)
    with pytest.raises(SourceConfigError) as info:
        DocumentFetcherAgent().list_documents("bad", DocumentFilter())
    assert str(info.value) == "source 'bad' uses unknown strategy 'missing'"


class ClosableStrategy(FakeStrategy):
    closed: ClassVar[int] = 0

    def close(self) -> None:
        type(self).closed += 1


def test_strategy_cached_per_source_and_closed(
    monkeypatch: pytest.MonkeyPatch, registries: Registry[type[LegalSource]]
) -> None:
    strategies: Registry[type[FetchStrategy]] = Registry("strategies")
    strategies.register("fake_strategy")(ClosableStrategy)
    monkeypatch.setattr("agents.fetch.document_fetcher.STRATEGIES", strategies)
    ClosableStrategy.closed = 0
    with DocumentFetcherAgent() as agent:
        agent.list_documents("fake", DocumentFilter())
        agent.list_documents("fake", DocumentFilter())
        assert FakeStrategy.built_with == ["https://fake.example"]
    assert ClosableStrategy.closed == 1
    agent.close()
    assert ClosableStrategy.closed == 1


def test_close_skips_strategy_without_close() -> None:
    agent = DocumentFetcherAgent()
    agent.list_documents("fake", DocumentFilter())
    agent.close()
