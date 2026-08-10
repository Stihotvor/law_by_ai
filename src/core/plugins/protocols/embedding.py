"""Embedding plugin protocol (ADR-0001).

Defines the interface for embedding models (Sentence Transformers, OpenAI, etc.).
"""

from typing import Protocol, runtime_checkable

from core.plugins.protocols.types import JsonDict


@runtime_checkable
class EmbeddingPlugin(Protocol):
    """Embedding model (Sentence Transformers, eval-selected, ADR-0009)."""

    def generate_embeddings(self, texts: list[str]) -> list[list[float]]: ...

    def get_model_info(self) -> JsonDict: ...

    def get_embedding_dimension(self) -> int: ...


__all__ = ["EmbeddingPlugin"]
