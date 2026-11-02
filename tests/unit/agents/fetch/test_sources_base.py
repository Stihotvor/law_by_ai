from typing import ClassVar

import pytest

from agents.fetch.contracts import (
    DocumentFilter,
    DocumentMeta,
    DocumentPage,
    DocumentRef,
    FetchedDocument,
)
from agents.fetch.registry import Registry
from agents.fetch.sources.base import SOURCES, LegalSource, _validate_source
from agents.fetch.strategies.base import STRATEGIES


class _Base(LegalSource):
    def list_documents(self, flt: DocumentFilter) -> DocumentPage:
        raise NotImplementedError

    def get_document_meta(self, ref: DocumentRef) -> DocumentMeta:
        raise NotImplementedError

    def fetch_document(self, ref: DocumentRef) -> FetchedDocument:
        raise NotImplementedError


def _reg() -> Registry[type[LegalSource]]:
    return Registry("sources", _validate_source)


def test_abstract() -> None:
    with pytest.raises(TypeError):
        LegalSource(object())  # type: ignore[abstract, arg-type]


def test_valid_subclass_registers() -> None:
    class Good(_Base):
        name: ClassVar[str] = "good"
        base_url: ClassVar[str] = "https://good.example"
        strategy_name: ClassVar[str] = "http"

    reg = _reg()
    reg.register("good")(Good)
    assert reg.get("good") is Good


def test_invalid_sources() -> None:
    class WrongName(_Base):
        name: ClassVar[str] = "other"
        base_url: ClassVar[str] = "https://x"
        strategy_name: ClassVar[str] = "http"

    class Http(_Base):
        name: ClassVar[str] = "http_src"
        base_url: ClassVar[str] = "http://x"
        strategy_name: ClassVar[str] = "http"

    class NoStrategy(_Base):
        name: ClassVar[str] = "no_strategy"
        base_url: ClassVar[str] = "https://x"
        strategy_name: ClassVar[str] = ""

    class Missing(_Base):
        pass

    cases: list[tuple[str, type]] = [
        ("wrong", WrongName),
        ("http_src", Http),
        ("no_strategy", NoStrategy),
        ("missing", Missing),
        ("plain", int),
    ]
    for name, cls in cases:
        with pytest.raises(TypeError):
            _reg().register(name)(cls)  # type: ignore[arg-type]


def test_real_sources_match_modules() -> None:
    import pkgutil

    import agents.fetch.sources as pkg

    stems = sorted(
        m.name for m in pkgutil.iter_modules(pkg.__path__) if m.name != "base" and m.name[0] != "_"
    )
    assert SOURCES.names() == tuple(stems)


def test_real_sources_consistent() -> None:
    for n in SOURCES.names():
        cls = SOURCES.get(n)
        assert cls.name == n
        assert cls.strategy_name in STRATEGIES
