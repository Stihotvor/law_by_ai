# Plugins (implementations)

Concrete providers implementing the protocols in `core/plugins/` (ADR-0001).
Selected and configured via `config/plugins.yaml`; swapping a backend is a
config change, not a code change.

- `postgresql.py` — DatabasePlugin (metadata, chunks, full-text search)
- `chroma.py` / `qdrant.py` — VectorDBPlugin (in-memory Chroma MVP → Qdrant)
- `memgraph.py` / `neo4j.py` — GraphDBPlugin (Memgraph MVP → Neo4j)
- `web_etl.py` / `git_etl.py` — ETLSourcePlugin
- `sentence_transformers.py` — EmbeddingPlugin (eval-selected, ADR-0009)
