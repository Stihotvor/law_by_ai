"""Plugin SPI protocols (ADR-0001).

The plugin protocols are defined as ``typing.Protocol`` interfaces — duck
typing, no ABC inheritance. Concrete implementations live in ``src/plugins/``
and are registered in ``config/plugins.yaml``; agents depend only on these
protocols, never on implementations.

All protocols are marked ``@runtime_checkable`` so :class:`PluginManager` can
validate registered classes at load time.
"""

from core.plugins.protocols.embedding import EmbeddingPlugin
from core.plugins.protocols.graph_db import GraphDBPlugin
from core.plugins.protocols.knowledge_source import KnowledgeSourcePlugin
from core.plugins.protocols.llm import LLMPlugin
from core.plugins.protocols.relational_db import RelationalDBPlugin
from core.plugins.protocols.reranking import RerankingPlugin
from core.plugins.protocols.types import JsonDict
from core.plugins.protocols.vector_db import VectorDBPlugin

__all__ = [
    "EmbeddingPlugin",
    "GraphDBPlugin",
    "JsonDict",
    "KnowledgeSourcePlugin",
    "LLMPlugin",
    "RelationalDBPlugin",
    "RerankingPlugin",
    "VectorDBPlugin",
]
