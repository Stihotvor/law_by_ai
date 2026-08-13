# Plugins (implementations)

> **DEPRECATED (ADR-0014).** The plugin system is being phased out for a
> one-person project. PostgreSQL is now a **direct integration**:
> `relational_db/postgres.py` provides `PostgreSQLStore`, used directly by
> agents/UI/tasks (no `PluginManager` routing). The remaining plugin types are
> retained as deprecated scaffolding until each backend becomes a direct
> dependency.

- `relational_db/postgres.py` — `PostgreSQLStore` (**direct integration**,
  schema via Alembic migrations, ADR-0014)
- `vector_db/…`, `graph_db/…`, `knowledge_source/…`, `embedding/…`, `llm/…`,
  `reranking/…` — deprecated placeholders (ADR-0014)
