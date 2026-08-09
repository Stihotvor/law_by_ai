"""Reranking plugin protocol (ADR-0001).

Defines the interface for reranking models (Cohere, local models, etc.).
Used for reranking retrieved documents in RAG pipelines.
"""

from typing import Protocol, runtime_checkable

from core.plugins.protocols.types import JsonDict


@runtime_checkable
class RerankingPlugin(Protocol):
    """Reranking model for document reordering in RAG pipelines."""

    def rerank(self, query: str, documents: list[JsonDict], top_k: int = 5) -> list[JsonDict]: ...


__all__ = ["RerankingPlugin"]
