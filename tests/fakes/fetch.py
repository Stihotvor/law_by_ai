"""Shared fake fetch source and strategy.

The fake strategy validates ids like a real one: a bad id raises
``InvalidReferenceError`` and an unknown source raises ``SourceConfigError``.
Tests register the fakes in local registries, never in the global ``SOURCES``.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import ClassVar

from agents.fetch.contracts import (
    DocumentFilter,
    DocumentMeta,
    DocumentPage,
    DocumentRef,
    FetchedDocument,
)
from agents.fetch.errors import InvalidReferenceError, SourceConfigError
from agents.fetch.sources.base import LegalSource

FAKE_SOURCE = "fake"
FAKE_STRATEGY = "fake_strategy"
FAKE_BASE = "https://example.invalid/fake"
FAKE_TITLE = "Ustawa testowa"
FAKE_BODY = "Art. 1. Treść ustawy."
FAKE_FETCHED_AT = datetime(2026, 1, 2, tzinfo=UTC)
FAKE_ID_PATTERN = re.compile(r"[0-9a-f]{32}\.txt")


class FakeStrategy:
    """Fetch strategy and ref builder for ``FakeSource``; records every read."""

    reads: ClassVar[list[DocumentRef]] = []

    def __init__(self, base_url: str) -> None:
        self._base = base_url.rstrip("/")

    def list_refs(self, source: str, flt: DocumentFilter) -> DocumentPage:
        return DocumentPage(items=())

    def make_ref(self, source: str, external_id: str) -> DocumentRef:
        if source != FAKE_SOURCE:
            raise SourceConfigError(f"no fake source {source!r}")
        if not FAKE_ID_PATTERN.fullmatch(external_id):
            raise InvalidReferenceError("unsafe external_id")
        return DocumentRef(
            source=source, external_id=external_id, url=f"{self._base}/{external_id}"
        )

    def get_meta(self, ref: DocumentRef) -> DocumentMeta:
        return DocumentMeta(ref=ref, title=FAKE_TITLE, extra={"k": "v"})

    def read(self, ref: DocumentRef) -> bytes:
        self.reads.append(ref)
        return FAKE_BODY.encode("utf-8")


class FakeSource(LegalSource):
    name: ClassVar[str] = FAKE_SOURCE
    base_url: ClassVar[str] = FAKE_BASE
    strategy_name: ClassVar[str] = FAKE_STRATEGY

    def list_documents(self, flt: DocumentFilter) -> DocumentPage:
        return self.strategy.list_refs(self.name, flt)

    def get_document_meta(self, ref: DocumentRef) -> DocumentMeta:
        return self.strategy.get_meta(ref)

    def fetch_document(self, ref: DocumentRef) -> FetchedDocument:
        return FetchedDocument(
            meta=self.strategy.get_meta(ref),
            content=self.strategy.read(ref),
            content_type="text/plain; charset=utf-8",
            fetched_at=FAKE_FETCHED_AT,
        )


STATIC_REF = DocumentRef(source="fake", external_id="1", url="https://fake.example/1")
STATIC_META = DocumentMeta(ref=STATIC_REF, title="t")
STATIC_PAGE = DocumentPage(items=(STATIC_REF,))
STATIC_DOC = FetchedDocument(
    meta=STATIC_META, content=b"x", fetched_at=datetime(2026, 1, 1, tzinfo=UTC)
)


class StaticFakeStrategy:
    """Strategy with fixed answers; records base URLs and reads. Not a ref builder."""

    built_with: ClassVar[list[str]] = []
    reads: ClassVar[list[DocumentRef]] = []

    def __init__(self, base_url: str) -> None:
        self.built_with.append(base_url)

    def list_refs(self, source: str, flt: DocumentFilter) -> DocumentPage:
        return STATIC_PAGE

    def get_meta(self, ref: DocumentRef) -> DocumentMeta:
        return STATIC_META

    def read(self, ref: DocumentRef) -> bytes:
        self.reads.append(ref)
        return b"x"


class StaticFakeSource(LegalSource):
    name: ClassVar[str] = "fake"
    base_url: ClassVar[str] = "https://fake.example"
    strategy_name: ClassVar[str] = "fake_strategy"

    def list_documents(self, flt: DocumentFilter) -> DocumentPage:
        return STATIC_PAGE

    def get_document_meta(self, ref: DocumentRef) -> DocumentMeta:
        return STATIC_META

    def fetch_document(self, ref: DocumentRef) -> FetchedDocument:
        self.strategy.read(ref)
        return STATIC_DOC
