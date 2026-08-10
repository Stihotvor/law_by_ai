"""Tests for core/plugins/manager.py (ADR-0001)."""

import sys
import types
from pathlib import Path

import pytest

from core.plugins.exceptions import PluginLoadError, PluginNotFoundError, PluginValidationError
from core.plugins.manager import ROOT_DIR, PluginManager


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


class LifecyclePlugin(FakeRelationalDB):
    initialize_calls = 0
    close_calls = 0

    def initialize(self):
        LifecyclePlugin.initialize_calls += 1

    def close(self):
        LifecyclePlugin.close_calls += 1


class BadRelationalDB:
    def save_document(self, document, tenant_id=None):
        return "doc1"


@pytest.fixture
def fake_plugins_module(monkeypatch):
    module = types.ModuleType("fake_plugins")
    module.FakeRelationalDB = FakeRelationalDB
    module.FakeVectorPlugin = FakeVectorPlugin
    module.LifecyclePlugin = LifecyclePlugin
    module.BadRelationalDB = BadRelationalDB
    monkeypatch.setitem(sys.modules, "fake_plugins", module)
    return module


def _write_registry(tmp_path: Path, content: str) -> PluginManager:
    config = tmp_path / "plugins.yaml"
    config.write_text(content)
    return PluginManager(config_path=config)


def test_load_registers_and_routes(fake_plugins_module, tmp_path):
    mgr = _write_registry(
        tmp_path,
        """
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
""",
    )
    mgr.load()

    assert isinstance(mgr.get_plugin("relational_db"), FakeRelationalDB)
    assert isinstance(mgr.get_plugin("vector_db"), FakeVectorPlugin)


def test_get_plugin_triggers_lazy_load(fake_plugins_module, tmp_path):
    mgr = _write_registry(
        tmp_path,
        """
plugins:
  relational_db:
    postgres:
      module: fake_plugins
      class: FakeRelationalDB
      active: true
""",
    )
    assert isinstance(mgr.get_plugin("relational_db"), FakeRelationalDB)


def test_inactive_plugin_is_not_active(fake_plugins_module, tmp_path):
    mgr = _write_registry(
        tmp_path,
        """
plugins:
  relational_db:
    postgres:
      module: fake_plugins
      class: FakeRelationalDB
      active: false
""",
    )
    mgr.load()
    assert mgr.get_plugin_options("relational_db") == ["postgres"]
    with pytest.raises(PluginNotFoundError):
        mgr.get_plugin("relational_db")


def test_unknown_type_raises(fake_plugins_module, tmp_path):
    mgr = _write_registry(
        tmp_path,
        """
plugins:
  not_a_type:
    x:
      module: fake_plugins
      class: FakeRelationalDB
""",
    )
    with pytest.raises(PluginLoadError):
        mgr.load()


def test_missing_module_raises(fake_plugins_module, tmp_path):
    mgr = _write_registry(
        tmp_path,
        """
plugins:
  relational_db:
    x:
      module: does_not_exist
      class: FakeRelationalDB
      active: true
""",
    )
    with pytest.raises(PluginLoadError):
        mgr.load()


def test_missing_class_raises(fake_plugins_module, tmp_path):
    mgr = _write_registry(
        tmp_path,
        """
plugins:
  relational_db:
    x:
      module: fake_plugins
      class: DoesNotExist
      active: true
""",
    )
    with pytest.raises(PluginLoadError):
        mgr.load()


def test_validation_rejects_non_conforming(fake_plugins_module, tmp_path):
    mgr = _write_registry(
        tmp_path,
        """
plugins:
  relational_db:
    bad:
      module: fake_plugins
      class: BadRelationalDB
      active: true
""",
    )
    with pytest.raises(PluginValidationError):
        mgr.load()


def test_missing_registry_file_raises():
    mgr = PluginManager(config_path="/nonexistent/plugins.yaml")
    with pytest.raises(PluginLoadError):
        mgr.load()


def test_lifecycle_initialize_and_close(fake_plugins_module, tmp_path):
    LifecyclePlugin.initialize_calls = 0
    LifecyclePlugin.close_calls = 0
    mgr = _write_registry(
        tmp_path,
        """
plugins:
  relational_db:
    lc:
      module: fake_plugins
      class: LifecyclePlugin
      active: true
""",
    )
    mgr.load()
    mgr.initialize()
    mgr.close()
    assert LifecyclePlugin.initialize_calls == 1
    assert LifecyclePlugin.close_calls == 1


def test_singleton_and_roots():
    from core.plugins.manager import plugin_manager

    assert isinstance(plugin_manager, PluginManager)
    assert (ROOT_DIR / "src").is_dir()
