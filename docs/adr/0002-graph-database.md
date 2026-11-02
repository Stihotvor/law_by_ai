---
status: proposed
---

# ADR-0002: Neo4j AuraDB Free as the graph database

## Context

Cross-reference tracking requires a graph database. The original plan started
with in-process NetworkX and targeted Neo4j/Memgraph later. NetworkX holds the
whole graph in process memory and serializes to disk — acceptable for small
graphs but not for tens of thousands of legal documents on a 4–6 GB RAM budget.

An earlier version of this ADR chose Memgraph for the MVP and Neo4j for
production, both behind a `GraphDBPlugin`. ADR-0014 deprecated the plugin system
and fixed the production stack: Neo4j AuraDB Free, cloud-managed.

## Decision

- **Neo4j AuraDB Free** is the graph database, for the MVP and for production.
- It is a direct integration. There is no `GraphDBPlugin` and no Memgraph.
- The free tier runs outside Docker Compose, so it adds no container and no
  local RAM.

## Consequences

- Cypher skills and query code carry over to any later Neo4j hosting.
- No graph container in docker-compose, which keeps the local RAM budget.
- The free tier has size limits. If the graph outgrows them, the move is to a
  paid AuraDB tier or self-hosted Neo4j with the same Cypher code.

## Alternatives Considered

- **Memgraph (MVP), Neo4j (production)** — two engines and a plugin layer for
  one real target. Dropped with the plugin system (ADR-0014).
- **NetworkX** — simplest but in-process memory and no query language.

## Related

- [ADR-0014](0014-hardcoded-postgresql.md) — fixed production stack
- [Architecture](../architecture.md) — Graph store
- [Intention](../intention.md) #18
