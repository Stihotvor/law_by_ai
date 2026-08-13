---
status: accepted
---

# ADR-0014: Hardcoded PostgreSQL integration; plugin system deprecated

## Context

The original architecture (ADR-0001) defined **seven protocol-based plugin
types** (`RelationalDB`, `VectorDB`, `GraphDB`, `KnowledgeSource`, `Embedding`,
`LLM`, `Reranking`) with YAML registration and a `PluginManager` routing layer,
so every backend could be swapped without touching agent code.

This project is maintained by **one person**. Maintaining seven interchangeable
abstraction layers for a single production backend each is a real maintenance
burden: every new feature must be expressed through the lowest common
denominator of a Protocol, every concrete implementation needs protocol
validation, and the YAML registry must stay in sync — all for backends we never
actually swap. The cost outweighs the benefit.

The relational store has exactly one real production target: **PostgreSQL**
(multi-tenant document store, users/tenants with RLS). The swap path for it
does not justify a plugin interface.

## Decision

1. **PostgreSQL is a hardcoded, direct integration.** The
   `RelationalDBPlugin` protocol indirection is removed; agents, UI, and tasks
   import `PostgreSQLStore` from `plugins.relational_db.postgres` directly (the
   UI auth adapter already did this in practice).
2. **The plugin system is deprecated.** No new plugin types or routing entries
   are added. Existing protocol/manager code stays in the tree, marked
   deprecated, and is removed incrementally as each integration is converted to
   a direct dependency. No `relational_db` entry may be registered in
   `config/plugins.yaml` again.
3. **Fixed production stack** (single provider per concern):
   - PostgreSQL — relational store, schema via Alembic migrations (issue #9)
   - Redis — Celery broker / result backend
   - Neo4j **AuraDB Free** — graph database (ADR-0002, cloud-managed)
   - Qdrant — vector store
   - Grafana Cloud (free tier) + **Grafana Alloy** locally — observability
     (ADR-0005)
   - OpenAI-compatible endpoints for LLM/SLM — each agent may use its own model
   - Cohere — reranking model
   - Embedding provider may differ from the LLM provider

## Consequences

- Simpler code: no Protocol validation, no YAML routing for the relational
  layer; agents call the store directly.
- Faster iteration for a single maintainer.
- Backend swaps (if ever needed) require code changes rather than a config
  change — accepted trade-off for a one-person project.
- The other six plugin types are retained only as deprecated scaffolding until
  their direct integrations land.
- Migration work (issue #9) is now the single source of truth for the
  PostgreSQL schema.

## Alternatives Considered

- **Keep all seven plugins (status quo)** — high abstraction cost, no real
  swap benefit for a one-person project.
- **Keep only RelationalDBPlugin, hardcode the rest** — half-measure; the same
  maintenance argument applies to every type with a single backend.

## Related

- [ADR-0001](0001-plugin-architecture.md) — plugin system (now superseded)
- [ADR-0002](0002-graph-database.md) — Neo4j AuraDB
- [ADR-0003](0003-multi-tenancy.md) — RLS isolation
- [Issue #9](https://github.com/Stihotvor/law_by_ai/issues/9) — DB migrations
- [Migrations guide](../migrations.md)
