---
status: proposed
---

# ADR-0001: Protocol-based plugins with YAML registration

## Context

The MVP plan originally used **ABCs** (abstract base classes) with
`importlib` auto-discovery of plugins from a directory. As the architecture
matured, we need a plugin mechanism that:

- lets backends be swapped without touching agent code,
- keeps the 4–6 GB RAM + SLM efficiency budget (no heavy introspection),
- makes the active plugin set explicit and reviewable in the repo,
- avoids fragile auto-discovery and class-hierarchy coupling.

## Decision

- Define each of the five plugin types as a **`typing.Protocol`** in
  `core/plugins/protocols.py` (Database, Vector DB, Graph DB, ETL Source,
  Embedding).
- Register concrete implementations in **`config/plugins.yaml`**.
- `PluginManager` reads the YAML, imports the class via `importlib`, and
  routes requests by plugin type.
- Agents depend only on the Protocol; they never import concrete plugins.

## Consequences

- Plugins are duck-typed and easily replaced (Chroma↔Qdrant, Memgraph↔Neo4j).
- Plugin inventory is explicit in one YAML file (good for ops/review).
- No inheritance hierarchy — simpler tests via lightweight fakes.
- Requires runtime validation that a registered class satisfies the Protocol.

## Alternatives Considered

- **ABCs + auto-discovery** — original plan; couples implementations to a
  base-class hierarchy and hides the active set.
- **Entry-point plugins (packaging)** — overkill for a self-hosted monolith.

## Related

- [Architecture](../architecture.md) — Plugin Architecture
- [Intention](../intention.md) #24
