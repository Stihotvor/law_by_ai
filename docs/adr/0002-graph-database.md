---
status: proposed
---

# ADR-0002: Memgraph (MVP) → Neo4j (production)

## Context

Cross-reference tracking requires a graph database. The original plan started
with in-process NetworkX and targeted Neo4j/Memgraph later. NetworkX holds the
whole graph in process memory and serializes to disk — acceptable for small
graphs but not for tens of thousands of legal documents on a 4–6 GB RAM budget.

## Decision

- **MVP**: **Memgraph** via a `GraphDBPlugin` implementation
  (`plugins/memgraph.py`). Memgraph is Cypher-compatible, in-memory, and has a
  small operational footprint.
- **Production**: **Neo4j** via `plugins/neo4j.py` behind the same Protocol.
- Migration = export graph data, swap the YAML config entry; agents unchanged.

## Consequences

- Cypher skills and query code carry over between MVP and production.
- Memgraph gives real graph semantics (vs. NetworkX in-process) without the
  full Neo4j footprint in MVP.
- Adds one more container to docker-compose; must fit the RAM budget.

## Alternatives Considered

- **NetworkX (MVP)** — simplest but in-process memory and no query language;
  migration work deferred to production.
- **Neo4j from day one** — heavier for MVP hardware budget.

## Related

- [Architecture](../architecture.md) — GraphDBPlugin, Migration Paths
- [Intention](../intention.md) #18
