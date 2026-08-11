"""Shared plugin fixtures (ADR-0001).

The :func:`fake_plugins_module` fixture registers a synthetic ``fake_plugins``
module in ``sys.modules`` exposing every fake class from
``tests/factories/plugins.py``. PluginManager loads plugins by module name via
``importlib``, so a registry entry such as ``module: fake_plugins`` /
``class: FakeRelationalDB`` resolves to our in-memory module exactly like a
real installed plugin.
"""

import sys
import types

import factories.plugins as plugin_factories
import pytest


@pytest.fixture
def fake_plugins_module(monkeypatch):
    """A ``fake_plugins`` module with every fake plugin class attached.

    Registered under the ``fake_plugins`` name in ``sys.modules`` so
    ``importlib.import_module("fake_plugins")`` finds it during load.
    """
    module = types.ModuleType("fake_plugins")
    for plugin_type, fake_class in plugin_factories.FAKE_PLUGINS.items():
        setattr(module, fake_class.__name__, fake_class)
        setattr(module, plugin_type, fake_class)
    monkeypatch.setitem(sys.modules, "fake_plugins", module)
    return module
