"""Graph database plugin protocol (ADR-0001).

Defines the interface for graph stores (Memgraph MVP, Neo4j production).
"""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class GraphDBPlugin(Protocol):
    """Graph store for entities and relations (Memgraph MVP, Neo4j production)."""

    def add_node(self, node_id: str, properties: dict[str, Any] | None = None) -> None: ...

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        relation: str,
        properties: dict[str, Any] | None = None,
    ) -> None: ...

    def get_related_nodes(
        self, node_id: str, relation: str | None = None
    ) -> list[dict[str, Any]]: ...

    def get_node(self, node_id: str) -> dict[str, Any] | None: ...

    def delete_node(self, node_id: str) -> None: ...

    def delete_edge(self, source_id: str, target_id: str, relation: str) -> None: ...

    def get_all_nodes(self) -> list[dict[str, Any]]: ...

    def get_all_edges(self) -> list[dict[str, Any]]: ...


__all__ = ["GraphDBPlugin"]
