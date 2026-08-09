"""Vector database plugin protocol (ADR-0001).

Defines the interface for vector stores (Chroma MVP, Qdrant production).
"""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class VectorDBPlugin(Protocol):
    """Vector store for embeddings (Chroma MVP, Qdrant production)."""

    def upsert_embeddings(
        self,
        collection: str,
        ids: list[str],
        embeddings: list[list[float]],
        metadata: list[dict[str, Any]] | None = None,
    ) -> None: ...

    def search_embeddings(
        self, collection: str, query_vector: list[float], *, limit: int = 10
    ) -> list[dict[str, Any]]: ...

    def delete_embeddings(self, collection: str, ids: list[str]) -> None: ...

    def create_collection(self, name: str) -> None: ...

    def delete_collection(self, name: str) -> None: ...


__all__ = ["VectorDBPlugin"]
