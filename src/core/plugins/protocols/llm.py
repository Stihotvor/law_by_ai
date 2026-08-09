"""LLM plugin protocol (ADR-0001).

Defines the interface for language models (OpenAI, Ollama, local SLMs).
Used for: user chats, RAG query generation, step-back prompting,
GraphRAG traversal, and other LLM-driven tasks.
"""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LLMPlugin(Protocol):
    """Language model for generation, RAG, and GraphRAG traversal."""

    def generate_response(self, prompt: str, context: dict[str, Any] | None = None) -> str: ...

    def step_back_prompt(self, question: str) -> str: ...

    def generate_rag_query(self, question: str) -> str: ...

    def traverse_graph(self, start_node: str, max_depth: int = 3) -> list[dict[str, Any]]: ...


__all__ = ["LLMPlugin"]
