"""Relational database plugin protocol (ADR-0001).

Defines the interface for persistent document storage with full-text search.
"""

from typing import Protocol, runtime_checkable

from core.plugins.protocols.types import JsonDict


@runtime_checkable
class RelationalDBPlugin(Protocol):
    """Persistent document storage (metadata, chunks, full-text search)."""

    def save_document(self, document: JsonDict, tenant_id: str | None = None) -> str: ...

    def get_document(self, document_id: str, tenant_id: str | None = None) -> JsonDict | None: ...

    def search_documents(
        self, query: str, *, limit: int = 10, tenant_id: str | None = None
    ) -> list[JsonDict]: ...

    def get_recent_changes(
        self, *, since: str | None = None, tenant_id: str | None = None
    ) -> list[JsonDict]: ...

    def delete_document(self, document_id: str, tenant_id: str | None = None) -> None: ...

    def update_document(
        self, document_id: str, document: JsonDict, tenant_id: str | None = None
    ) -> None: ...


__all__ = ["RelationalDBPlugin"]
