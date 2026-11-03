"""Document fetcher agent: resolves a source and fetches raw documents."""

from types import TracebackType
from typing import Protocol, Self

import agents.fetch.formats
import agents.fetch.sources
import agents.fetch.strategies  # noqa: F401  (triggers autoload)
from agents.fetch.contracts import (
    DocumentFilter,
    DocumentMeta,
    DocumentPage,
    DocumentRef,
    FetchedDocument,
)
from agents.fetch.errors import (
    DocumentRejectedError,
    InvalidTenantError,
    SourceConfigError,
    UnknownSourceError,
)
from agents.fetch.formats.base import FormatError, charset_of, find_parser
from agents.fetch.formats.pdf import NoTextLayerError, PdfParser
from agents.fetch.ocr.errors import OcrError
from agents.fetch.ocr.manager import get_ocr_manager
from agents.fetch.registry import UnknownNameError
from agents.fetch.sources.base import SOURCES, LegalSource
from agents.fetch.strategies.base import STRATEGIES, FetchStrategy

PARSE_ERRORS = (FormatError, OcrError)


class RejectionChecker(Protocol):
    def is_rejected(self, source_url: str) -> bool: ...


class NeverRejected:
    # TODO: replace with the store-backed checker when rejected-document tracking exists.
    def is_rejected(self, source_url: str) -> bool:
        return False


def _check_source(source: str, ref: DocumentRef) -> None:
    if ref.source != source:
        raise ValueError(f"ref.source {ref.source!r} does not match source {source!r}")


_MAX_TENANT_LEN = 64


def _check_tenant(tenant_id: object) -> None:
    if tenant_id is None:
        return
    if not isinstance(tenant_id, str):
        raise InvalidTenantError("tenant_id must be a string")
    if not tenant_id or len(tenant_id) > _MAX_TENANT_LEN:
        raise InvalidTenantError(f"tenant_id must be 1 to {_MAX_TENANT_LEN} characters")
    if any(ord(c) < 32 or ord(c) == 127 for c in tenant_id):
        raise InvalidTenantError("tenant_id has control characters")


class DocumentFetcherAgent:
    def __init__(self, rejection: RejectionChecker | None = None) -> None:
        self._rejection: RejectionChecker = rejection or NeverRejected()
        self._strategies: dict[str, FetchStrategy] = {}

    def close(self) -> None:
        """Close cached strategies that have a ``close`` method."""
        strategies, self._strategies = list(self._strategies.values()), {}
        for strategy in strategies:
            closer = getattr(strategy, "close", None)
            if callable(closer):
                closer()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def _resolve(self, source: str) -> LegalSource:
        try:
            source_cls = SOURCES.get(source)
        except UnknownNameError as exc:
            raise UnknownSourceError(f"unknown source {source[:64]!r}") from exc
        try:
            strategy_cls = STRATEGIES.get(source_cls.strategy_name)
        except UnknownNameError as exc:
            raise SourceConfigError(
                f"source {source!r} uses unknown strategy {source_cls.strategy_name!r}"
            ) from exc
        strategy = self._strategies.get(source)
        if strategy is None:
            strategy = self._strategies[source] = strategy_cls(source_cls.base_url)
        return source_cls(strategy)

    def list_documents(self, source: str, flt: DocumentFilter) -> DocumentPage:
        return self._resolve(source).list_documents(flt)

    def get_document_meta(self, source: str, ref: DocumentRef) -> DocumentMeta:
        _check_source(source, ref)
        return self._resolve(source).get_document_meta(ref)

    def fetch_document(
        self, source: str, ref: DocumentRef, *, tenant_id: str | None = None
    ) -> FetchedDocument:
        _check_tenant(tenant_id)
        _check_source(source, ref)
        if self._rejection.is_rejected(ref.url):
            raise DocumentRejectedError(f"document rejected: {ref.source}/{ref.external_id}")
        result = self._resolve(source).fetch_document(ref)
        return result.model_copy(update={"tenant_id": tenant_id})

    def parse(self, doc_bytes: bytes, name: str, mime: str | None = None) -> str:
        """Turn raw bytes into plain text. Raises FormatError subclasses or OcrError (PARSE_ERRORS).

        UnsupportedFormatError: no parser matches the name or MIME type.
        TextLimitError: extracted text is over the character cap.
        """
        parser = find_parser(name, mime)
        try:
            return parser.parse(doc_bytes, charset=charset_of(mime))
        except NoTextLayerError:
            if not isinstance(parser, PdfParser):
                raise
            return get_ocr_manager().read_pdf(doc_bytes)
