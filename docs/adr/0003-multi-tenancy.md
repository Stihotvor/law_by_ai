---
status: proposed
---

# ADR-0003: Shared document storage, per-tenant state

## Context

The platform is multi-tenant from day 1. The original design stored every
document, chunk, and user record with a `tenant_id`, plus separate collections
per tenant in the vector store and subgraphs per tenant in the graph store.

Legal documents are largely public/shared reference material; only
tenant-owned state (notes, chats, processing states, annotations) is truly
private. Fully duplicating documents per tenant wastes the 4–6 GB RAM budget.

## Decision

- **Documents are shared storage**: a single `LegalDocument` corpus is
  read-accessible by all tenants (public legislation, case law, etc.).
- **Per-tenant state is isolated**: notes, chats, states, and annotations are
  keyed by `tenant_id` and never shared.
- **Enforcement**:
  - PostgreSQL — row-level security (RLS) on tenant-owned tables; documents
    are read-only shared rows.
  - Chroma/Qdrant — partitions/collections scoped by tenant for embeddings of
    tenant-private content; shared docs use a shared partition.
  - Memgraph/Neo4j — subgraph per tenant.
- **Automated leak tests** assert no tenant can read or write another tenant's
  state.

## Consequences

- Efficient storage and embedding of the shared corpus (embedded once).
- Clear security boundary: shared vs. tenant-owned data.
- Requires careful query auditing so `tenant_id` is never omitted on private
  tables; leak tests enforce this.

## Alternatives Considered

- **Full per-tenant duplication** — simplest isolation but wasteful (embedded
  copies of every document per tenant).
- **Single shared table, no RLS** — not acceptable for privacy.

## Related

- [Architecture](../architecture.md) — Multi-Tenant Isolation, PostgreSQL
- [Intention](../intention.md) #21, #50, #51
