---
status: new
---

# Architecture Decision Records

> Architecture Decision Records (ADRs) capture the "why" behind significant
> architecture choices. They follow the
> [ADR template](https://github.com/joelparkerhenderson/architecture-decision-record).

## Status

| ADR | Title | Status | Date |
|-----|-------|--------|------|
| [ADR-0001](0001-plugin-architecture.md) | Protocol-based plugins with YAML registration | Proposed | 2026-07-31 |
| [ADR-0002](0002-graph-database.md) | Memgraph (MVP) → Neo4j (production) | Proposed | 2026-07-31 |
| [ADR-0003](0003-multi-tenancy.md) | Shared document storage, per-tenant state | Proposed | 2026-07-31 |
| [ADR-0004](0004-auth-rbac.md) | JWT auth + RBAC (admin/user) | Proposed | 2026-07-31 |
| [ADR-0005](0005-observability.md) | structlog + OTel → Grafana Alloy → Grafana Cloud | Proposed | 2026-07-31 |
| [ADR-0006](0006-celery-reliability.md) | Celery retries + in-DB failed-task registry | Proposed | 2026-07-31 |
| [ADR-0007](0007-document-diffs.md) | Git-backed document-level diffs | Proposed | 2026-07-31 |
| [ADR-0008](0008-mvp-scope.md) | Citations, filters, bureaucracy assistant in MVP | Proposed | 2026-07-31 |
| [ADR-0009](0009-model-evals.md) | Embedding/OCR/hybrid-search evaluation for Polish | Proposed | 2026-07-31 |
| [ADR-0010](0010-health-checks.md) | Container health checks | Proposed | 2026-07-31 |
| [ADR-0011](0011-sla-budget.md) | Efficiency budget (4–6 GB + SLM) and basic SLAs | Proposed | 2026-07-31 |

## How to add an ADR

1. Copy the template below into a new file `docs/adr/NNNN-title.md`.
2. Assign the next number.
3. Set status to `Proposed`.
4. Add the row to the status table.
5. When accepted, change status to `Accepted` and note the decision date.
6. Link the ADR from the relevant section of the [Architecture](../architecture.md) doc.

## Template

```markdown
---
status: proposed
---

# ADR-NNNN: <Title>

## Context

<Why is this decision needed? What problem does it solve?>

## Decision

<What is the decision? Be specific and concrete.>

## Consequences

<What are the trade-offs, risks, and follow-up work?>

## Alternatives Considered

- <Option A> — <why rejected>
- <Option B> — <why rejected>

## Related

- <link to other ADRs, issues, or docs>
```
