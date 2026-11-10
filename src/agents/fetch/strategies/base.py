"""Fetch strategy protocol and registry."""

from typing import Protocol, runtime_checkable

from agents.fetch.contracts import DocumentFilter, DocumentMeta, DocumentPage, DocumentRef
from agents.fetch.registry import Registry


@runtime_checkable
class FetchStrategy(Protocol):
    def __init__(self, base_url: str) -> None: ...

    def list_refs(self, source: str, flt: DocumentFilter) -> DocumentPage: ...

    def get_meta(self, ref: DocumentRef) -> DocumentMeta: ...

    def read(self, ref: DocumentRef) -> bytes: ...


@runtime_checkable
class RefBuilder(Protocol):
    """A strategy that can build a ``DocumentRef`` from a source id."""

    def make_ref(self, source: str, external_id: str) -> DocumentRef: ...


STRATEGIES: Registry[type[FetchStrategy]] = Registry("strategies")
