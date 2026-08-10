"""Plugin registration and access facade (issue #7, ADR-0001).

The single entry point agents and tasks use to reach plugins. It re-exports
the process-wide :class:`PluginManager` singleton and delegates the plugin
type routing — concrete implementations live in ``src/plugins/`` and are
registered in ``src/config/plugins.yaml``.
"""

from pathlib import Path

from core.plugins.manager import DEFAULT_CONFIG_PATH, PluginManager, plugin_manager

# Packaged registry path (same file DEFAULT_CONFIG_PATH points at).
PLUGINS_CONFIG_PATH = Path(__file__).resolve().parent / "plugins.yaml"


def get_plugin(plugin_type: str):
    """Return the active plugin of ``plugin_type`` (raise if none)."""
    return plugin_manager.get_plugin(plugin_type)


def get_plugin_options(plugin_type: str) -> list[str]:
    """Names of all registered plugins of ``plugin_type`` (inactive included)."""
    return plugin_manager.get_plugin_options(plugin_type)


def initialize_plugins() -> None:
    """Call ``initialize()`` on every registered plugin (startup hook)."""
    plugin_manager.initialize()


def close_plugins() -> None:
    """Call ``close()`` on every registered plugin (shutdown hook)."""
    plugin_manager.close()


__all__ = [
    "DEFAULT_CONFIG_PATH",
    "PLUGINS_CONFIG_PATH",
    "PluginManager",
    "close_plugins",
    "get_plugin",
    "get_plugin_options",
    "initialize_plugins",
    "plugin_manager",
]
