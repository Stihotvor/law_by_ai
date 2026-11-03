"""Document fetcher agent: resolves a source and fetches raw documents."""

import importlib
from typing import Protocol

from agents.fetch.contracts import (
    DocumentFilter,
    DocumentMeta,
    DocumentPage,
    DocumentRef,
    FetchedDocument,
)
from agents.fetch.errors import DocumentRejectedError, SourceConfigError, UnknownSourceError
from agents.fetch.formats.base import FormatError, charset_of, find_parser
from agents.fetch.formats.image import finish_ocr_text
from agents.fetch.formats.pdf import NoTextLayerError, PdfParser
from agents.fetch.ocr.errors import OcrError
from agents.fetch.ocr.manager import get_ocr_manager
from agents.fetch.registry import UnknownNameError
from agents.fetch.sources.base import SOURCES, LegalSource
from agents.fetch.strategies.base import STRATEGIES

PARSE_ERRORS = (FormatError, OcrError)

for _package in ("agents.fetch.sources", "agents.fetch.strategies", "agents.fetch.formats"):
    importlib.import_module(_package)  # triggers autoload


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
        return source_cls(strategy_cls(source_cls.base_url))

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
            return finish_ocr_text(get_ocr_manager().read_pdf(doc_bytes))
