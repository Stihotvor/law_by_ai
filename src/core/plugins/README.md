# Plugin API (SPI)

Interface layer of the plugin system (ADR-0001): `typing.Protocol`s, not ABCs.

- `protocols.py` — the five plugin `Protocol`s: DatabasePlugin, VectorDBPlugin,
  GraphDBPlugin, ETLSourcePlugin, EmbeddingPlugin
- `manager.py` — `PluginManager`: YAML-driven dynamic loading and type routing
- `exceptions.py` — plugin-specific errors
- `utils.py` — shared plugin utilities

Concrete implementations live in `src/plugins/` and are registered in
`config/plugins.yaml`. Agents depend on these protocols, never on
implementations — that is what makes backends swappable.
