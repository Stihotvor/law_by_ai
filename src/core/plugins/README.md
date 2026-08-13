# Plugin API (SPI)

> **DEPRECATED (ADR-0014).** PostgreSQL is a direct integration
> (`plugins.relational_db.postgres.PostgreSQLStore`), not a plugin. The
> protocol/manager layer below is retained only as deprecated scaffolding and
> is removed as each backend becomes a direct dependency. Do **not** register a
> `relational_db` entry in `config/plugins.yaml`.

- `protocols/` — the plugin `Protocol`s (one file each, deprecated):
  - `vector_db.py` — `VectorDBPlugin`
  - `graph_db.py` — `GraphDBPlugin`
  - `knowledge_source.py` — `KnowledgeSourcePlugin`
  - `embedding.py` — `EmbeddingPlugin`
  - `llm.py` — `LLMPlugin`
  - `reranking.py` — `RerankingPlugin`
  - `types.py` — shared type aliases (`JsonDict`)
- `manager.py` — `PluginManager`: YAML-driven dynamic loading and type routing
- `exceptions.py` — plugin-specific errors
