---
status: proposed
---

# ADR-0010: Container health checks

## Context

Docker-Compose runs many services (PostgreSQL, Chroma/Qdrant, Memgraph/Neo4j,
Redis, Celery workers, Streamlit, Alloy). For SLA tracking and fast failure
detection, each service must expose liveness/health.

## Decision

- Every container defines a **Docker healthcheck** (HTTP endpoint or
  CLI-based probe).
- Services expose a health endpoint (e.g., FastAPI `/healthz` for API-facing
  services; DB engines use their native probes).
- Health state is:
  - visible via `docker inspect`/Compose status,
  - exported into OTel metrics (service up/down) for the Grafana dashboards,
  - used by Compose `depends_on: condition: service_healthy` to order startup.

## Consequences

- Faster failure detection and cleaner startup ordering.
- Health metrics feed SLA reporting (ADR-0011).
- Slight per-container overhead; health checks are kept lightweight.

## Alternatives Considered

- **No health checks, rely on manual `docker ps`** — too slow for SLA goals.
- **Kubernetes-style probes** — overkill for Docker-Compose MVP.

## Related

- [Architecture](../architecture.md) — Technology Stack, docker-compose
- [Intention](../intention.md) #26, #54
