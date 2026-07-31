---
status: proposed
---

# ADR-0011: Efficiency budget (4–6 GB + SLM) and basic SLAs

## Context

The platform's north-star value depends on it being **fast and cheap to run**.
The original plan had no hardware budget and no measurable service targets.

## Decision

- **Hardware budget**: the full stack must operate well within **~4–6 GB RAM**
  using a **small local model (SLM)**. This is a constraint on model choice
  (embeddings, OCR, LLM), vector store mode, Celery concurrency, and service
  footprint. Where options differ, the more RAM-efficient choice wins.
- **Basic SLA targets** (MVP, tracked via OTel/Grafana):
  - Hybrid search latency: **< 3 s** p95 on the reference corpus/hardware.
  - Document processing (fetch → OCR → chunk → embed → graph): bounded budget
    per document, tracked per task in the failed-task registry.
  - Availability: services report healthy via health checks (ADR-0010);
    observed availability is reported, not contractual.
- Targets are **baselines** to be refined after the Phase 3–4 evals
  (ADR-0009).

## Consequences

- Concrete, measurable targets for the efficiency mandate.
- Some features must be descoped if they break the RAM budget.
- SLA measurement is built in from the start (OTel → Grafana).

## Alternatives Considered

- **No stated budget/SLAs** — efficiency remains aspirational and unverifiable.
- **Large-model-first, optimize later** — contradicts the mandate.

## Related

- [Architecture](../architecture.md) — Architecture Principles, Observability
- [Intention](../intention.md) #7, #52, #53, #54
