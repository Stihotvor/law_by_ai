"""PluginManager — YAML-driven dynamic loading and type routing (ADR-0001).

Reads plugin registration from ``config/plugins.yaml``, imports each concrete
class via ``importlib``, validates it against its ``typing.Protocol``, and
routes requests by plugin type. Agents depend on the protocols in
``core.plugins.protocols`` and never import concrete plugins directly.

Lifecycle: ``initialize()`` → use (``get_plugin``) → ``close()``.
Selection is configuration-driven: the ``active`` flag in the YAML (overridable
by ``config.settings``) determines which implementation serves each type.
"""

import importlib
from pathlib import Path
from typing import Any

import yaml

from core.plugins.exceptions import (
    PluginLoadError,
    PluginNotFoundError,
    PluginValidationError,
)
from core.plugins.protocols import (
    EmbeddingPlugin,
    GraphDBPlugin,
    KnowledgeSourcePlugin,
    LLMPlugin,
    RelationalDBPlugin,
    RerankingPlugin,
    VectorDBPlugin,
)

# Repository root: <repo>/src/core/plugins/manager.py -> <repo>/
ROOT_DIR = Path(__file__).resolve().parents[3]

# The registry ships inside the packaged ``config`` module (src/config/), so it
# survives in the Docker image and stays consistent with docs/architecture.md.
DEFAULT_CONFIG_PATH = ROOT_DIR / "src" / "config" / "plugins.yaml"

# Plugin type (as used in config/plugins.yaml) -> runtime-checkable protocol.
TYPE_TO_PROTOCOL: dict[str, type[Any]] = {
    "relational_db": RelationalDBPlugin,
    "vector_db": VectorDBPlugin,
    "graph_db": GraphDBPlugin,
    "knowledge_source": KnowledgeSourcePlugin,
    "embedding": EmbeddingPlugin,
    "llm": LLMPlugin,
    "reranking": RerankingPlugin,
}


class PluginManager:
    """Loads plugins from a YAML registry and routes requests by type."""

    def __init__(self, config_path: str | Path | None = None) -> None:
        self._config_path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
        self._plugins: dict[str, list[tuple[str, Any]]] = {}
        self._active: dict[str, Any] = {}
        self._loaded = False

    # --- loading ------------------------------------------------------------
    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    def load(self) -> None:
        """Read the YAML registry and import every registered plugin."""
        try:
            with self._config_path.open(encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
        except FileNotFoundError as exc:
            raise PluginLoadError(f"plugin registry not found: {self._config_path}") from exc
        except yaml.YAMLError as exc:
            raise PluginLoadError(f"invalid plugin registry YAML: {exc}") from exc

        if not isinstance(data, dict):
            raise PluginLoadError(
                f"plugin registry root must be a mapping in {self._config_path}, "
                f"got {type(data).__name__}"
            )

        registry = data.get("plugins", {})
        if not isinstance(registry, dict):
            raise PluginLoadError(
                f"'plugins' must be a mapping in {self._config_path}, got {type(registry).__name__}"
            )

        self._plugins = {ptype: [] for ptype in TYPE_TO_PROTOCOL}
        self._active = {}
        for plugin_type, entries in registry.items():
            if plugin_type not in TYPE_TO_PROTOCOL:
                raise PluginLoadError(f"unknown plugin type {plugin_type!r} in {self._config_path}")
            for name, spec in entries.items():
                instance = self._import(spec, name=name, plugin_type=plugin_type)
                self._plugins[plugin_type].append((name, instance))
                if spec.get("active", False):
                    self._active[plugin_type] = instance
        self._loaded = True

    def _import(self, spec: dict[str, Any], *, name: str, plugin_type: str) -> Any:
        module_name = spec.get("module")
        class_name = spec.get("class")
        if not module_name or not class_name:
            raise PluginLoadError(f"plugin {plugin_type}/{name!r} needs both 'module' and 'class'")
        try:
            module = importlib.import_module(module_name)
        except ImportError as exc:
            raise PluginLoadError(
                f"cannot import module {module_name!r} for plugin {plugin_type}/{name!r}: {exc}"
            ) from exc
        try:
            plugin_cls = getattr(module, class_name)
        except AttributeError as exc:
            raise PluginLoadError(
                f"class {class_name!r} not found in {module_name!r} for "
                f"plugin {plugin_type}/{name!r}"
            ) from exc
        try:
            instance = plugin_cls()
        except Exception as exc:
            raise PluginLoadError(
                f"cannot instantiate {module_name}.{class_name} for "
                f"plugin {plugin_type}/{name!r}: {exc}"
            ) from exc

        protocol = TYPE_TO_PROTOCOL[plugin_type]
        if not isinstance(instance, protocol):
            raise PluginValidationError(
                f"{module_name}.{class_name} does not satisfy {protocol.__name__}"
            )
        return instance

    # --- routing -------------------------------------------------------------
    def get_plugin(self, plugin_type: str) -> Any:
        """Return the active plugin for a type (raise if none)."""
        self._ensure_loaded()
        try:
            return self._active[plugin_type]
        except KeyError as exc:
            raise PluginNotFoundError(
                f"no active plugin of type {plugin_type!r} "
                f"(registered: {[n for n, _ in self._plugins.get(plugin_type, [])]})"
            ) from exc

    def get_plugin_options(self, plugin_type: str) -> list[str]:
        """Names of all registered plugins of a type (inactive included)."""
        self._ensure_loaded()
        return [n for n, _ in self._plugins.get(plugin_type, [])]

    # --- lifecycle ------------------------------------------------------------
    def initialize(self) -> None:
        self._ensure_loaded()
        for pairs in self._plugins.values():
            for _, instance in pairs:
                init = getattr(instance, "initialize", None)
                if callable(init):
                    init()

    def close(self) -> None:
        self._ensure_loaded()
        for pairs in self._plugins.values():
            for _, instance in pairs:
                close = getattr(instance, "close", None)
                if callable(close):
                    close()


# Process-wide singleton (architecture.md).
plugin_manager = PluginManager()


__all__ = [
    "DEFAULT_CONFIG_PATH",
    "ROOT_DIR",
    "PluginManager",
    "plugin_manager",
]
