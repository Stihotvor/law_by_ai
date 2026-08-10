"""Knowledge source plugin protocol (ADR-0001).

Defines the interface for content sources that fetch legal/knowledge content
for ingestion (web, git, filesystem, APIs, etc.).
"""

from typing import Any, Protocol, runtime_checkable

from core.plugins.protocols.types import JsonDict


@runtime_checkable
class KnowledgeSourcePlugin(Protocol):
    """Content sources for legal/knowledge content ingestion."""

    def fetch(self, source: JsonDict, **kwargs: Any) -> list[JsonDict]: ...

    def validate_config(self, config: JsonDict) -> bool: ...

    def list_sources(self) -> list[JsonDict]: ...


__all__ = ["KnowledgeSourcePlugin"]
