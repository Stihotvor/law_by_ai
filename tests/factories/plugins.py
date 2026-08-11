"""Fake plugin classes and factories for tests (ADR-0001).

The fake classes satisfy the plugin protocols and are importable under the
``fake_plugins`` module name so that ``PluginManager.load()`` can import them
via ``importlib`` exactly like real plugins: the shared
``fake_plugins_module`` fixture registers this module in ``sys.modules``
(see ``tests/fixtures/plugins.py``).

The ``make_*`` functions are factories that return fresh instances, used for
protocol conformance checks (``tests/unit/plugins/test_protocols.py``).
"""


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


# Plugin type -> (fake class, factory) for every protocol (TYPE_TO_PROTOCOL).
FAKE_PLUGINS: dict[str, type] = {
    "relational_db": FakeRelationalDB,
    "vector_db": FakeVectorDB,
    "graph_db": FakeGraphDB,
    "knowledge_source": FakeKnowledgeSource,
    "embedding": FakeEmbedding,
    "llm": FakeLLM,
    "reranking": FakeReranking,
}


def make_fake_relational_db() -> FakeRelationalDB:
    return FakeRelationalDB()


def make_fake_vector_db() -> FakeVectorDB:
    return FakeVectorDB()


def make_fake_graph_db() -> FakeGraphDB:
    return FakeGraphDB()


def make_fake_knowledge_source() -> FakeKnowledgeSource:
    return FakeKnowledgeSource()


def make_fake_embedding() -> FakeEmbedding:
    return FakeEmbedding()


def make_fake_llm() -> FakeLLM:
    return FakeLLM()


def make_fake_reranking() -> FakeReranking:
    return FakeReranking()


__all__ = [
    "FAKE_PLUGINS",
    "FakeEmbedding",
    "FakeGraphDB",
    "FakeKnowledgeSource",
    "FakeLLM",
    "FakeRelationalDB",
    "FakeReranking",
    "FakeVectorDB",
    "make_fake_embedding",
    "make_fake_graph_db",
    "make_fake_knowledge_source",
    "make_fake_llm",
    "make_fake_relational_db",
    "make_fake_reranking",
    "make_fake_vector_db",
]
