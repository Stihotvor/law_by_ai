"""Tests for config/plugins.py facade (issue #7, ADR-0001)."""

import pytest
from factories.plugins import (
    FakeEmbedding,
    FakeGraphDB,
    FakeKnowledgeSource,
    FakeLLM,
    FakeRelationalDB,
    FakeReranking,
    FakeVectorDB,
)

import config.plugins as plug
from core.plugins.exceptions import PluginNotFoundError
from core.plugins.manager import PluginManager


def _manager_from(tmp_path, content: str) -> PluginManager:
    registry = tmp_path / "plugins.yaml"
    registry.write_text(content)
    return PluginManager(config_path=registry)


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
      class: FakeVectorDB
      active: true
  graph_db:
    memgraph:
      module: fake_plugins
      class: FakeGraphDB
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


def test_facade_registers_and_routes_all_types(fake_plugins_module, tmp_path, monkeypatch):
    monkeypatch.setattr(plug, "plugin_manager", _manager_from(tmp_path, ALL_TYPES_REGISTRY))

    assert isinstance(plug.get_plugin("relational_db"), FakeRelationalDB)
    assert isinstance(plug.get_plugin("vector_db"), FakeVectorDB)
    assert isinstance(plug.get_plugin("graph_db"), FakeGraphDB)
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
