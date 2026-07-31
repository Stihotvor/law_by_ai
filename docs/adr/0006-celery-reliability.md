---
status: proposed
---

# ADR-0006: Celery retries + in-DB failed-task registry

## Context

Long-running work (fetch, OCR, chunk, embed, graph build) runs on Celery.
With a human-in-the-loop model, a failed task should not be silently lost —
the user must be able to see what failed and re-run it.

## Decision

- **Retry policies**: Celery tasks configure exponential-backoff retries with a
  bounded `max_retries`; timeouts are tuned to the RAM budget.
- **In-DB failure registry**: when a task exhausts retries or is detected as
  stuck/unprocessed, a row is written to the PostgreSQL `failed_tasks` table
  (task id, name, args, error, state, timestamps).
- **Re-run from UI**: the Streamlit UI lists unprocessed/failed in-DB tasks and
  offers a "re-run" action that re-enqueues them.
- **Detection**: a periodic sweep compares queued/processing tasks against
  expected progress to surface stuck tasks.

## Consequences

- No silent data loss; users can recover from transient failures manually.
- Adds a small DB table and one sweep task.
- Retry + backoff must be tuned per task type to avoid hammering services on
  the constrained hardware.

## Alternatives Considered

- **Dead-letter broker queue only** — requires manual broker surgery and gives
  no user-facing recovery.
- **No retries (fail loudly)** — poor UX for a human-in-the-loop MVP.

## Related

- [Architecture](../architecture.md) — Celery + Redis, PostgreSQL
- [Intention](../intention.md) #23, #42
