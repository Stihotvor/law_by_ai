# Plugin API (SPI)

Interface layer of the plugin system (ADR-0001): `typing.Protocol`s, not ABCs.

- `protocols/` — the plugin `Protocol`s (one file each):
  - `relational_db.py` — `RelationalDBPlugin` (PostgreSQL, SQLite)
  - `vector_db.py` — `VectorDBPlugin` (Chroma, Qdrant)
  - `graph_db.py` — `GraphDBPlugin` (Memgraph, Neo4j)
  - `knowledge_source.py` — `KnowledgeSourcePlugin` (web, git, filesystem)
  - `embedding.py` — `EmbeddingPlugin` (Sentence Transformers, OpenAI)
  - `llm.py` — `LLMPlugin` (OpenAI, Ollama, local SLMs)
  - `reranking.py` — `RerankingPlugin` (Cohere, local models)
  - `types.py` — shared type aliases (`JsonDict`)
- `manager.py` — `PluginManager`: YAML-driven dynamic loading and type routing
- `exceptions.py` — plugin-specific errors

Concrete implementations live in `src/plugins/` and are registered in
`config/plugins.yaml`. Agents depend on these protocols, never on
implementations — that is what makes backends swappable.
