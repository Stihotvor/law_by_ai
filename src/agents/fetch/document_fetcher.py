"""Document fetcher agent: resolves a source and fetches raw documents."""

from typing import Protocol

import agents.fetch.sources
import agents.fetch.strategies  # noqa: F401  (triggers autoload)
from agents.fetch.contracts import (
    DocumentFilter,
    DocumentMeta,
    DocumentPage,
    DocumentRef,
    FetchedDocument,
)
from agents.fetch.errors import DocumentRejectedError, SourceConfigError
from agents.fetch.registry import UnknownNameError
from agents.fetch.sources.base import SOURCES, LegalSource
from agents.fetch.strategies.base import STRATEGIES


class RejectionChecker(Protocol):
    def is_rejected(self, source_url: str) -> bool: ...


class NeverRejected:
    # TODO: replace with the store-backed checker when rejected-document tracking exists.
    def is_rejected(self, source_url: str) -> bool:
        return False


def _check_source(source: str, ref: DocumentRef) -> None:
    if ref.source != source:
        raise ValueError(f"ref.source {ref.source!r} does not match source {source!r}")


class DocumentFetcherAgent:
    def __init__(self, rejection: RejectionChecker | None = None) -> None:
        self._rejection: RejectionChecker = rejection or NeverRejected()

    def _resolve(self, source: str) -> LegalSource:
        cls = SOURCES.get(source)
        try:
            strategy_cls = STRATEGIES.get(cls.strategy_name)
        except UnknownNameError as exc:
            raise SourceConfigError(
                f"source {source!r} uses unknown strategy {cls.strategy_name!r}"
            ) from exc
        return cls(strategy_cls(cls.base_url))

    def list_documents(self, source: str, flt: DocumentFilter) -> DocumentPage:
        return self._resolve(source).list_documents(flt)

    def get_document_meta(self, source: str, ref: DocumentRef) -> DocumentMeta:
        _check_source(source, ref)
        return self._resolve(source).get_document_meta(ref)

    def fetch_document(
        self, source: str, ref: DocumentRef, *, tenant_id: str | None = None
    ) -> FetchedDocument:
        _check_source(source, ref)
        if self._rejection.is_rejected(ref.url):
            raise DocumentRejectedError(f"document rejected: {ref.url}")
        result = self._resolve(source).fetch_document(ref)
        return result.model_copy(update={"tenant_id": tenant_id})
