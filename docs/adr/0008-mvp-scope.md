---
status: proposed
---

# ADR-0008: Citations, filters, bureaucracy assistant in MVP

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

## Consequences

- MVP scope grows but delivers the core value proposition (saved time/money).
- Adds a `BureaucracyAssistantAgent`, citation extraction, and filter UI to
  Phase 5–6 work.
- Keeps change-tracking and visualizations out of the critical path.

## Alternatives Considered

- **Citations/filters post-MVP** — undermines the north-star metric.
- **Bureaucracy assistant as "later"** — contradicts priority-agent status.

## Related

- [Architecture](../architecture.md) — Search & Q&A, Agents, Data Model
- [Intention](../intention.md) #15, #32, #33, #41, #55
