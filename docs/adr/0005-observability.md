---
status: proposed
---

# ADR-0005: structlog + OTel → Grafana Alloy → Grafana Cloud

## Context

A fast, self-hosted legal platform needs visibility into task failures, search
latency, and queue health — without blowing the RAM budget or leaking sensitive
legal data. The original plan had no observability stack.

## Decision

- **Logs**: `structlog` emitting JSON, with PII stripped at the source.
- **Metrics & traces**: OpenTelemetry SDK in the UI, Celery workers, and
  agents (task duration, queue depth, search latency, error rates).
- **Export path**: OTel → **Grafana Alloy** (local collector) → **Grafana
  Cloud**.
- **Privacy (anonymization)**: no tenant names, user identifiers, document
  content, or query text in telemetry. Tenant IDs are hashed; document/query
  content is excluded entirely.
- Included in the **MVP**.

## Consequences

- Consistent, queryable JSON logs plus distributed traces for debugging.
- SLA targets (ADR-0011) become measurable via the Grafana dashboards.
- Slight CPU/RAM overhead from the SDK and Alloy — kept minimal and accounted
  for in the efficiency budget.
- Anonymization is a first-class requirement: any span/log attribute that
  could carry PII is stripped by convention and tested.

## Alternatives Considered

- **Self-hosted ELK/Loki + Prometheus + Grafana** — heavier and more moving
  parts for the budget.
- **No observability in MVP** — unacceptable for reliability goals.

## Related

- [Architecture](../architecture.md) — Observability
- [Intention](../intention.md) #25, #52
