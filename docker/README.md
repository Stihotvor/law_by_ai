# Docker

Containers and orchestration (issue #6; ADR-0010 health checks, ADR-0011
efficiency budget).

- `Dockerfile` — `python:3.11-slim`, two-stage uv build, non-root runtime user
- `docker-compose.yml` — services: `app` (Streamlit), `celery-worker`,
  `postgres`, `redis`; a healthcheck per container; internal network; `pgdata`
  volume

Quickstart:

```bash
docker compose -f docker/docker-compose.yml up --build
```

Vector store (Chroma/Qdrant), graph store (Memgraph/Neo4j), and observability
(Grafana Alloy) containers are added in later phases.
