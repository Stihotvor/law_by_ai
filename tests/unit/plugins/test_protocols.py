"""Tests for core/plugins/protocols (ADR-0001)."""

import pytest
from factories.plugins import (
    make_fake_embedding,
    make_fake_graph_db,
    make_fake_knowledge_source,
    make_fake_llm,
    make_fake_relational_db,
    make_fake_reranking,
    make_fake_vector_db,
)

from core.plugins.protocols import (
    EmbeddingPlugin,
    GraphDBPlugin,
    JsonDict,
    KnowledgeSourcePlugin,
    LLMPlugin,
    RelationalDBPlugin,
    RerankingPlugin,
    VectorDBPlugin,
)

# (protocol, factory) pairs: one per plugin type the manager routes.
CONFORMING_PAIRS = [
    (RelationalDBPlugin, make_fake_relational_db),
    (VectorDBPlugin, make_fake_vector_db),
    (GraphDBPlugin, make_fake_graph_db),
    (KnowledgeSourcePlugin, make_fake_knowledge_source),
    (EmbeddingPlugin, make_fake_embedding),
    (LLMPlugin, make_fake_llm),
    (RerankingPlugin, make_fake_reranking),
]


class NotARelationalDB:
    def save_document(self, document, tenant_id=None):
        return "doc1"


@pytest.mark.parametrize("protocol, factory", CONFORMING_PAIRS)
def test_conforming_classes_satisfy_protocols(protocol, factory):
    assert isinstance(factory(), protocol)


def test_non_conforming_class_fails_runtime_check():
    assert not isinstance(NotARelationalDB(), RelationalDBPlugin)


def test_json_dict_type_alias():
    # JsonDict is a type alias for dict[str, Any]
    d: JsonDict = {"key": "value"}
    assert isinstance(d, dict)
    assert d["key"] == "value"
