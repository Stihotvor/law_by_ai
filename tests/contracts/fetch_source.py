"""Contract checks for fetch sources and the strategies that build refs.

Plain assert functions; the tests that run them live in
``tests/unit/agents/fetch/test_source_contract.py``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pytest

from agents.fetch.contracts import DocumentRef, FetchedDocument
from agents.fetch.errors import InvalidReferenceError, SourceConfigError
from agents.fetch.sources.base import LegalSource, _validate_source
from agents.fetch.strategies.base import RefBuilder

UNREGISTERED = "unregistered"


@dataclass(frozen=True)
class SourceCase:
    """One source class with its strategy and the ids the contract feeds it.

    ``fetch_ref`` is None when ``fetch_document`` needs the network; such
    sources have their fetch covered by a MockTransport test instead.
    """

    source_cls: type[LegalSource]
    strategy_cls: Callable[[str], Any]
    valid_id: str = ""
    expected_url: str = ""
    too_long_id: str = ""
    fetch_ref: DocumentRef | None = None

    @property
    def name(self) -> str:
        return self.source_cls.name

    def strategy(self) -> Any:
        return self.strategy_cls(self.source_cls.base_url)


def invalid_ids(case: SourceCase) -> tuple[str, ...]:
    """Ids every ref builder must refuse; the full document URL comes first."""
    return (case.expected_url, "", "../x", f" {case.valid_id}", case.too_long_id)


def check_ref_builder(case: SourceCase) -> None:
    if not (case.valid_id and case.expected_url and case.too_long_id):
        raise ValueError(f"{case.name}: ref builder case needs valid_id, expected_url, too_long_id")
    strategy = case.strategy()
    assert isinstance(strategy, RefBuilder)
    expected = DocumentRef(source=case.name, external_id=case.valid_id, url=case.expected_url)
    assert strategy.make_ref(case.name, case.valid_id) == expected
    for bad in invalid_ids(case):
        with pytest.raises(InvalidReferenceError):
            strategy.make_ref(case.name, bad)
    with pytest.raises(SourceConfigError):
        strategy.make_ref(UNREGISTERED, case.valid_id)


def check_legal_source(case: SourceCase) -> None:
    _validate_source(case.name, case.source_cls)
    if case.fetch_ref is None:
        return
    doc = case.source_cls(case.strategy()).fetch_document(case.fetch_ref)
    assert isinstance(doc, FetchedDocument)
    assert doc.meta.ref == case.fetch_ref
