from typing import Any, ClassVar, cast

import pytest
from fakes.fetch import STATIC_DOC as DOC
from fakes.fetch import STATIC_META as META
from fakes.fetch import STATIC_PAGE as PAGE
from fakes.fetch import STATIC_REF as REF
from fakes.fetch import StaticFakeSource, StaticFakeStrategy

from agents.fetch.contracts import (
    DocumentFilter,
    DocumentMeta,
    DocumentPage,
    DocumentRef,
    FetchedDocument,
)
from agents.fetch.document_fetcher import DocumentFetcherAgent
from agents.fetch.errors import (
    DocumentRejectedError,
    FetchTransportError,
    InvalidTenantError,
    SourceConfigError,
    UnknownSourceError,
)
from agents.fetch.registry import Registry, UnknownNameError
from agents.fetch.sources.base import LegalSource, _validate_source
from agents.fetch.strategies.base import FetchStrategy


class RecordingSource(StaticFakeSource):
    """Fake source that records each call it gets."""

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
    """Swap in local registries holding the static fakes."""
    PrivateStrategy.kwargs.clear()
    sources: Registry[type[LegalSource]] = Registry("sources", _validate_source)
    strategies: Registry[type[FetchStrategy]] = Registry("strategies")
    sources.register("fake")(StaticFakeSource)
    strategies.register("fake_strategy")(StaticFakeStrategy)
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
    """A source naming an unknown strategy raises a config error."""

    class Bad(StaticFakeSource):
        """Source that names a missing strategy."""

        name: ClassVar[str] = "bad"
        strategy_name: ClassVar[str] = "missing"

    registries.register("bad")(Bad)
    with pytest.raises(SourceConfigError):
        DocumentFetcherAgent().list_documents("bad", DocumentFilter())


def test_rejected() -> None:
    """A rejected document is refused before the strategy is built."""
    with pytest.raises(DocumentRejectedError):
        DocumentFetcherAgent(Rejecting()).fetch_document("fake", REF)
    assert StaticFakeStrategy.reads == []
    assert StaticFakeStrategy.built_with == []


def test_source_mismatch() -> None:
    agent = DocumentFetcherAgent()
    with pytest.raises(ValueError, match="does not match"):
        agent.fetch_document("other", REF)
    with pytest.raises(ValueError, match="does not match"):
        agent.get_document_meta("other", REF)


def test_strategy_built_with_base_url() -> None:
    """The strategy is built with the source's base URL."""
    DocumentFetcherAgent().list_documents("fake", DocumentFilter())
    assert StaticFakeStrategy.built_with == ["https://fake.example"]


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
    assert str(rej.value) == "document rejected: 'fake/1'"
    assert REF.url not in str(rej.value)
    with pytest.raises(ValueError, match="does not match") as mismatch:
        DocumentFetcherAgent().get_document_meta("other", REF)
    assert str(mismatch.value) == "ref.source 'fake' does not match source 'other'"


def test_unknown_strategy_message(registries: Registry[type[LegalSource]]) -> None:
    """The unknown strategy error names the source and strategy."""

    class Bad(StaticFakeSource):
        """Source that names a missing strategy."""

        name: ClassVar[str] = "bad"
        strategy_name: ClassVar[str] = "missing"

    registries.register("bad")(Bad)
    with pytest.raises(SourceConfigError) as info:
        DocumentFetcherAgent().list_documents("bad", DocumentFilter())
    assert str(info.value) == "source 'bad' uses unknown strategy 'missing'"


class ClosableStrategy(StaticFakeStrategy):
    """Static strategy that counts close calls."""

    closed: ClassVar[int] = 0

    def close(self) -> None:
        type(self).closed += 1


def test_strategy_cached_per_source_and_closed(
    monkeypatch: pytest.MonkeyPatch, registries: Registry[type[LegalSource]]
) -> None:
    """One strategy per source is built and closed once."""
    strategies: Registry[type[FetchStrategy]] = Registry("strategies")
    strategies.register("fake_strategy")(ClosableStrategy)
    monkeypatch.setattr("agents.fetch.document_fetcher.STRATEGIES", strategies)
    ClosableStrategy.closed = 0
    with DocumentFetcherAgent() as agent:
        agent.list_documents("fake", DocumentFilter())
        agent.list_documents("fake", DocumentFilter())
        assert StaticFakeStrategy.built_with == ["https://fake.example"]
    assert ClosableStrategy.closed == 1
    agent.close()
    assert ClosableStrategy.closed == 1


def test_close_skips_strategy_without_close() -> None:
    agent = DocumentFetcherAgent()
    agent.list_documents("fake", DocumentFilter())
    agent.close()


@pytest.mark.parametrize("bad", ["", "x" * 65, "a\nb", "a\x7f", "a b", "t\n", 5, b"t"])
def test_invalid_tenant_rejected(bad: object) -> None:
    with pytest.raises(InvalidTenantError) as info:
        DocumentFetcherAgent().fetch_document("fake", REF, tenant_id=cast(Any, bad))
    assert "x" * 65 not in str(info.value)


def test_valid_tenant_boundary() -> None:
    doc = DocumentFetcherAgent().fetch_document("fake", REF, tenant_id="t" * 64)
    assert doc.tenant_id == "t" * 64


class PrivateStrategy(StaticFakeStrategy):
    """Static strategy that records the private-host flag it gets."""

    kwargs: ClassVar[list[dict[str, bool]]] = []

    def __init__(self, base_url: str, allow_private_hosts: bool = False) -> None:
        super().__init__(base_url)
        self.kwargs.append(
            {"allow_private_hosts": allow_private_hosts} if allow_private_hosts else {}
        )


class PrivateSource(StaticFakeSource):
    """Static source that opts in to private hosts."""

    name: ClassVar[str] = "priv"
    allow_private_hosts: ClassVar[bool] = True


def test_private_host_opt_in_forwarded(
    monkeypatch: pytest.MonkeyPatch, registries: Registry[type[LegalSource]]
) -> None:
    strategies: Registry[type[FetchStrategy]] = Registry("strategies")
    strategies.register("fake_strategy")(PrivateStrategy)
    monkeypatch.setattr("agents.fetch.document_fetcher.STRATEGIES", strategies)
    registries.register("priv")(PrivateSource)
    DocumentFetcherAgent().list_documents("priv", DocumentFilter())
    assert PrivateStrategy.kwargs == [{"allow_private_hosts": True}]


def test_never_rejected_warns_once(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(DocumentFetcherAgent, "_warned_never_rejected", False)
    with caplog.at_level("WARNING"):
        DocumentFetcherAgent()
        DocumentFetcherAgent()
        DocumentFetcherAgent(Rejecting())
    assert len(caplog.records) == 1


def test_close_closes_all_then_raises_first_error(
    monkeypatch: pytest.MonkeyPatch, registries: Registry[type[LegalSource]]
) -> None:
    """Close closes every strategy, then raises the first error."""

    class Boom(StaticFakeStrategy):
        """Strategy whose close fails."""

        def close(self) -> None:
            raise RuntimeError("first")

    agent = DocumentFetcherAgent()
    good = ClosableStrategy("x")
    ClosableStrategy.closed = 0
    agent._strategies = {"a": Boom("x"), "b": good, "c": Boom("x")}
    with pytest.raises(RuntimeError, match="first"):
        agent.close()
    assert ClosableStrategy.closed == 1


def test_flag_without_strategy_keyword_is_a_config_error(
    registries: Registry[type[LegalSource]],
) -> None:
    """The private-host flag needs a strategy that accepts it."""
    registries.register("priv")(PrivateSource)
    with pytest.raises(SourceConfigError, match="allow_private_hosts"):
        DocumentFetcherAgent().list_documents("priv", DocumentFilter())
    assert StaticFakeStrategy.built_with == []


def test_rejection_message_escapes_and_cuts_id() -> None:
    ref = REF.model_copy(update={"external_id": "a\nb" + "x" * 100})
    with pytest.raises(DocumentRejectedError) as rej:
        DocumentFetcherAgent(Rejecting()).fetch_document("fake", ref)
    assert "\n" not in str(rej.value)
    assert len(str(rej.value)) < 100


def test_closed_agent_does_not_rebuild_strategies() -> None:
    agent = DocumentFetcherAgent()
    agent.close()
    with pytest.raises(FetchTransportError, match="closed"):
        agent.list_documents("fake", DocumentFilter())


def test_invalid_tenant_message_is_exact() -> None:
    with pytest.raises(InvalidTenantError) as info:
        DocumentFetcherAgent().fetch_document("fake", REF, tenant_id="a b")
    assert str(info.value) == "tenant_id must match [A-Za-z0-9_-]{1,64}"


def test_private_host_flag_without_keyword_message_is_exact(
    registries: Registry[type[LegalSource]],
) -> None:
    registries.register("priv")(PrivateSource)
    with pytest.raises(SourceConfigError) as info:
        DocumentFetcherAgent().list_documents("priv", DocumentFilter())
    assert str(info.value) == "strategy does not support allow_private_hosts"


def test_private_host_strategy_gets_the_base_url(
    monkeypatch: pytest.MonkeyPatch, registries: Registry[type[LegalSource]]
) -> None:
    strategies: Registry[type[FetchStrategy]] = Registry("strategies")
    strategies.register("fake_strategy")(PrivateStrategy)
    monkeypatch.setattr("agents.fetch.document_fetcher.STRATEGIES", strategies)
    registries.register("priv")(PrivateSource)
    DocumentFetcherAgent().list_documents("priv", DocumentFilter())
    assert PrivateStrategy.built_with == ["https://fake.example"]


def test_no_warning_when_a_checker_is_given_first(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(DocumentFetcherAgent, "_warned_never_rejected", False)
    with caplog.at_level("WARNING"):
        DocumentFetcherAgent(Rejecting())
    assert caplog.records == []
    assert DocumentFetcherAgent._warned_never_rejected is False


def test_never_rejected_warning_text_is_exact(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(DocumentFetcherAgent, "_warned_never_rejected", False)
    with caplog.at_level("WARNING"):
        DocumentFetcherAgent()
    assert [r.getMessage() for r in caplog.records] == [
        "no rejection checker given: rejected documents are not blocked"
    ]


def test_new_agent_is_open() -> None:
    assert DocumentFetcherAgent()._closed is False


def test_closed_message_is_exact() -> None:
    agent = DocumentFetcherAgent()
    agent.close()
    with pytest.raises(FetchTransportError) as info:
        agent.list_documents("fake", DocumentFilter())
    assert str(info.value) == "closed"


def test_rejection_label_is_cut_at_64_characters() -> None:
    ref = REF.model_copy(update={"external_id": "x" * 100})
    with pytest.raises(DocumentRejectedError) as rej:
        DocumentFetcherAgent(Rejecting()).fetch_document("fake", ref)
    label = ("fake/" + "x" * 100)[:64]
    assert str(rej.value) == f"document rejected: {label!r}"


def test_parse_uses_the_mime_type_when_the_name_has_no_suffix() -> None:
    assert DocumentFetcherAgent().parse(b"<p>x</p>", "page", "text/html") == "x"


def test_parse_passes_the_mime_charset_to_the_parser() -> None:
    # 0xA3 is "£" in latin-1 and "Ł" in cp1250 (the fallback).
    mime = "text/plain; charset=iso-8859-1"
    assert DocumentFetcherAgent().parse(b"\xa3", "a.txt", mime) == "£"
    assert DocumentFetcherAgent().parse(b"\xa3", "a.txt") == "Ł"


def test_make_ref_without_ref_builder_raises() -> None:
    with pytest.raises(NotImplementedError, match="source does not support fetch by id"):
        DocumentFetcherAgent().make_ref("fake", "1")
