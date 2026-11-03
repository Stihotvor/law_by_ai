"""Legal source ABC and registry."""

from abc import ABC, abstractmethod
from typing import ClassVar

from agents.fetch.contracts import (
    DocumentFilter,
    DocumentMeta,
    DocumentPage,
    DocumentRef,
    FetchedDocument,
)
from agents.fetch.registry import Registry
from agents.fetch.strategies.base import FetchStrategy


class LegalSource(ABC):
    name: ClassVar[str]
    base_url: ClassVar[str]
    strategy_name: ClassVar[str]

    def __init__(self, strategy: FetchStrategy) -> None:
        self.strategy = strategy

    @abstractmethod
    def list_documents(self, flt: DocumentFilter) -> DocumentPage: ...

    @abstractmethod
    def get_document_meta(self, ref: DocumentRef) -> DocumentMeta: ...

    @abstractmethod
    def fetch_document(self, ref: DocumentRef) -> FetchedDocument:
        """Return raw bytes, no parsing, tenant_id None."""


def _validate_source(name: str, cls: type[LegalSource]) -> None:
    if not (isinstance(cls, type) and issubclass(cls, LegalSource)):
        raise TypeError(f"{cls!r} is not a LegalSource subclass")
    if getattr(cls, "name", None) != name:
        raise TypeError(f"source name must equal registered name {name!r}")
    if not str(getattr(cls, "base_url", "")).startswith("https://"):
        raise TypeError(f"source {name!r}: base_url must start with https://")
    if not getattr(cls, "strategy_name", ""):
        raise TypeError(f"source {name!r}: strategy_name must be non-empty")


SOURCES: Registry[type[LegalSource]] = Registry("sources", _validate_source)
