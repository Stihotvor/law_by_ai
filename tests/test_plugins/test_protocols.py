"""Tests for core/plugins/protocols (ADR-0001)."""

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


class FakeRelationalDB:
    def save_document(self, document, tenant_id=None):
        return "doc1"

    def get_document(self, document_id, tenant_id=None):
        return None

    def search_documents(self, query, *, limit=10, tenant_id=None):
        return []

    def get_recent_changes(self, *, since=None, tenant_id=None):
        return []

    def delete_document(self, document_id, tenant_id=None):
        pass

    def update_document(self, document_id, document, tenant_id=None):
        pass


class FakeVectorDB:
    def upsert_embeddings(self, collection, ids, embeddings, metadata=None):
        pass

    def search_embeddings(self, collection, query_vector, *, limit=10):
        return []

    def delete_embeddings(self, collection, ids):
        pass

    def create_collection(self, name):
        pass

    def delete_collection(self, name):
        pass


class FakeGraphDB:
    def add_node(self, node_id, properties=None):
        pass

    def add_edge(self, source_id, target_id, relation, properties=None):
        pass

    def get_related_nodes(self, node_id, relation=None):
        return []

    def get_node(self, node_id):
        return None

    def delete_node(self, node_id):
        pass

    def delete_edge(self, source_id, target_id, relation):
        pass

    def get_all_nodes(self):
        return []

    def get_all_edges(self):
        return []


class FakeKnowledgeSource:
    def fetch(self, source, **kwargs):
        return []

    def validate_config(self, config):
        return True

    def list_sources(self):
        return []


class FakeEmbedding:
    def generate_embeddings(self, texts):
        return [[0.0] for _ in texts]

    def get_model_info(self):
        return {"name": "fake"}

    def get_embedding_dimension(self):
        return 0


class FakeLLM:
    def generate_response(self, prompt, context=None):
        return "response"

    def step_back_prompt(self, question):
        return "step-back: " + question

    def generate_rag_query(self, question):
        return "rag: " + question

    def traverse_graph(self, start_node, max_depth=3):
        return []


class FakeReranking:
    def rerank(self, query, documents, top_k=5):
        return documents[:top_k]


class NotARelationalDB:
    def save_document(self, document, tenant_id=None):
        return "doc1"


def test_conforming_classes_satisfy_protocols():
    assert isinstance(FakeRelationalDB(), RelationalDBPlugin)
    assert isinstance(FakeVectorDB(), VectorDBPlugin)
    assert isinstance(FakeGraphDB(), GraphDBPlugin)
    assert isinstance(FakeKnowledgeSource(), KnowledgeSourcePlugin)
    assert isinstance(FakeEmbedding(), EmbeddingPlugin)
    assert isinstance(FakeLLM(), LLMPlugin)
    assert isinstance(FakeReranking(), RerankingPlugin)


def test_non_conforming_class_fails_runtime_check():
    assert not isinstance(NotARelationalDB(), RelationalDBPlugin)


def test_json_dict_type_alias():
    # JsonDict is a type alias for dict[str, Any]
    d: JsonDict = {"key": "value"}
    assert isinstance(d, dict)
    assert d["key"] == "value"
