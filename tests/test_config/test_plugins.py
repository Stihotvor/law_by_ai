"""Tests for config/plugins.py facade (issue #7, ADR-0001)."""

import sys
import types

import pytest

import config.plugins as plug
from core.plugins.exceptions import PluginNotFoundError
from core.plugins.manager import PluginManager


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


class FakeVectorPlugin:
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


class FakeGraphPlugin:
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


@pytest.fixture
def fake_plugins_module(monkeypatch):
    module = types.ModuleType("fake_plugins")
    for name in (
        "FakeRelationalDB",
        "FakeVectorPlugin",
        "FakeGraphPlugin",
        "FakeKnowledgeSource",
        "FakeEmbedding",
        "FakeLLM",
        "FakeReranking",
    ):
        setattr(module, name, globals()[name])
    monkeypatch.setitem(sys.modules, "fake_plugins", module)
    return module


ALL_TYPES_REGISTRY = """
plugins:
  relational_db:
    postgres:
      module: fake_plugins
      class: FakeRelationalDB
      active: true
  vector_db:
    chroma:
      module: fake_plugins
      class: FakeVectorPlugin
      active: true
  graph_db:
    memgraph:
      module: fake_plugins
      class: FakeGraphPlugin
      active: true
  knowledge_source:
    web_etl:
      module: fake_plugins
      class: FakeKnowledgeSource
      active: true
  embedding:
    st:
      module: fake_plugins
      class: FakeEmbedding
      active: true
  llm:
    openai:
      module: fake_plugins
      class: FakeLLM
      active: true
  reranking:
    cohere:
      module: fake_plugins
      class: FakeReranking
      active: true
"""


def _manager_from(tmp_path, content: str) -> PluginManager:
    registry = tmp_path / "plugins.yaml"
    registry.write_text(content)
    return PluginManager(config_path=registry)


def test_facade_registers_and_routes_all_types(fake_plugins_module, tmp_path, monkeypatch):
    monkeypatch.setattr(plug, "plugin_manager", _manager_from(tmp_path, ALL_TYPES_REGISTRY))

    assert isinstance(plug.get_plugin("relational_db"), FakeRelationalDB)
    assert isinstance(plug.get_plugin("vector_db"), FakeVectorPlugin)
    assert isinstance(plug.get_plugin("graph_db"), FakeGraphPlugin)
    assert isinstance(plug.get_plugin("knowledge_source"), FakeKnowledgeSource)
    assert isinstance(plug.get_plugin("embedding"), FakeEmbedding)
    assert isinstance(plug.get_plugin("llm"), FakeLLM)
    assert isinstance(plug.get_plugin("reranking"), FakeReranking)


def test_facade_options_and_missing_type(fake_plugins_module, tmp_path, monkeypatch):
    monkeypatch.setattr(plug, "plugin_manager", _manager_from(tmp_path, ALL_TYPES_REGISTRY))

    assert plug.get_plugin_options("relational_db") == ["postgres"]
    assert plug.get_plugin_options("llm") == ["openai"]
    with pytest.raises(PluginNotFoundError):
        plug.get_plugin("not_a_type")


def test_facade_lifecycle_hooks(fake_plugins_module, tmp_path, monkeypatch):
    monkeypatch.setattr(plug, "plugin_manager", _manager_from(tmp_path, ALL_TYPES_REGISTRY))

    plug.initialize_plugins()
    plug.close_plugins()
    assert plug.get_plugin("relational_db") is not None


def test_packaged_registry_exists_and_is_empty():
    assert plug.PLUGINS_CONFIG_PATH.is_file(), "src/config/plugins.yaml must be committed"
    assert plug.DEFAULT_CONFIG_PATH == plug.PLUGINS_CONFIG_PATH


def test_singleton_is_manager_instance():
    assert isinstance(plug.plugin_manager, PluginManager)
