# Docker

Containers and orchestration (issue #6; ADR-0010 health checks, ADR-0011
efficiency budget).

- `Dockerfile` — `python:3.13-slim`, multi-stage uv build (`builder` → `base` →
  `runtime`/`test`), non-root runtime user. Dev extras (pytest, etc.) are
  installed **only** in the `test` target, never in `runtime`.
- `docker-compose.yml` — services: `app` (Streamlit), `celery-worker`,
  `postgres`, `redis`; a healthcheck per container; internal network; `pgdata`
  volume.
  - The `test` service is gated behind `profiles: ["test"]`: a plain
    `docker compose up` never builds or starts it, keeping prod lean.

Run the production/dev stack:

```bash
docker compose -f docker/docker-compose.yml up --build
```

Run the test suite against live postgres and redis (builds the `test` target,
boots only postgres+redis, runs integration-marked tests; app and worker are
not started):

```bash
docker compose --profile test -f docker/docker-compose.yml run --rm test
```

Vector store (Chroma/Qdrant), graph store (Memgraph/Neo4j), and observability
(Grafana Alloy) containers are added in later phases.