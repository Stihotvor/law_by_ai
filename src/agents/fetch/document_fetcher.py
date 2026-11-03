"""Document fetcher agent: resolves a source and fetches raw documents."""

import importlib
import inspect
import logging
import re
import threading
from types import TracebackType
from typing import Any, Protocol, Self, cast

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
from agents.fetch.formats.text import finish_ocr_text
from agents.fetch.ocr.errors import OcrError
from agents.fetch.ocr.manager import get_ocr_manager
from agents.fetch.registry import UnknownNameError
from agents.fetch.sources.base import SOURCES, LegalSource
from agents.fetch.strategies.base import STRATEGIES, FetchStrategy

_log = logging.getLogger(__name__)
_warned_never_rejected = False

_TENANT_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")

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


def _check_tenant(tenant_id: object) -> None:
    if tenant_id is None:
        return
    if not isinstance(tenant_id, str) or not _TENANT_RE.fullmatch(tenant_id):
        raise InvalidTenantError("tenant_id must match [A-Za-z0-9_-]{1,64}")


def _build(strategy_cls: type[FetchStrategy], source_cls: type[LegalSource]) -> FetchStrategy:
    accepts = "allow_private_hosts" in inspect.signature(strategy_cls).parameters
    if source_cls.allow_private_hosts and accepts:
        return cast(Any, strategy_cls)(source_cls.base_url, allow_private_hosts=True)
    return strategy_cls(source_cls.base_url)


class DocumentFetcherAgent:
    def __init__(self, rejection: RejectionChecker | None = None) -> None:
        global _warned_never_rejected
        if rejection is None and not _warned_never_rejected:
            _warned_never_rejected = True
            _log.warning("no rejection checker given: rejected documents are not blocked")
        self._rejection: RejectionChecker = rejection or NeverRejected()
        self._strategies: dict[str, FetchStrategy] = {}
        self._lock = threading.Lock()

    def close(self) -> None:
        """Close cached strategies that have a ``close`` method."""
        with self._lock:
            strategies, self._strategies = list(self._strategies.values()), {}
        first: Exception | None = None
        for strategy in strategies:
            closer = getattr(strategy, "close", None)
            try:
                if callable(closer):
                    closer()
            except Exception as exc:
                first = first or exc
        if first is not None:
            raise first

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
        with self._lock:
            strategy = self._strategies.get(source)
            if strategy is None:
                strategy = self._strategies[source] = _build(strategy_cls, source_cls)
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
            return finish_ocr_text(get_ocr_manager().read_pdf(doc_bytes))
