---
status: proposed
---

# ADR-0008: MVP scope

## Context

The Intention doc listed several features as "planned". Based on the revised
priorities (efficiency-first MVP that delivers real value), some must move into
the MVP scope:

- Search must return **citations with confidence** — the primary value of a
  legal tool.
- Users must be able to narrow results by **document type, dates,
  jurisdiction**.
- The **bureaucracy/form assistant** is the most user-visible daily-use
  feature and was explicitly marked as a priority agent.

## Decision

The following are **MUST be in the MVP**:

- **Citations**: every search/analysis result includes exact law article
  citations, a confidence score, and a direct source link. Data model gains a
  `Citation` entity (law, article, paragraph, confidence, source_url).
- **Faceted filters**: search supports filters for document type, dates,
  jurisdiction, court, etc.
- **Bureaucracy assistant**: a dedicated agent (`BureaucracyAssistantAgent`)
  that walks users through administrative procedures step by step, backed by
  the document corpus and RAG.
- **Authentication and RBAC**: login, and the `admin` and `user` roles
  (ADR-0013).
- **Tenant isolation tests**: tests prove that one tenant never reads or writes
  another tenant's data (ADR-0003).
- **Observability and health checks**: structured logs and traces (ADR-0005),
  and container health checks (ADR-0010).
- **Human in the loop**: agents produce drafts. A person reviews and approves
  them, and new documents wait for admin approval before users see them.
- **Annotation**: users can annotate documents.
- **Information-only answers**: every answer follows ADR-0015.

Document diffs (ADR-0007) are not in the MVP critical path.

## Consequences

- MVP scope grows but delivers the core value proposition (saved time/money).
- Adds a `BureaucracyAssistantAgent`, citation extraction, and filter UI to
  Phase 5–6 work.
- Keeps change-tracking (document diffs) and visualizations out of the
  critical path.

## Alternatives Considered

- **Citations/filters post-MVP** — undermines the north-star metric.
- **Bureaucracy assistant as "later"** — contradicts priority-agent status.

## Related

- [ADR-0003](0003-multi-tenancy.md), [ADR-0005](0005-observability.md),
  [ADR-0007](0007-document-diffs.md), [ADR-0010](0010-health-checks.md),
  [ADR-0013](0013-streamlit-authenticator.md),
  [ADR-0015](0015-information-only-answers.md)
- [Architecture](../architecture.md) — Search & Q&A, Agents, Data Model
- [Intention](../intention.md) #15, #32, #33, #41, #55
