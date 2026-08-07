# Tasks

Celery task layer for long-running work (ADR-0006). Broker and result backend:
Redis (MVP); PostgreSQL result backend in production.

- `celery_app.py` — Celery application (broker/backend from `REDIS_URL`)
- `etl_tasks.py` — wrappers around agent methods (fetch, process, ...)
- `failed_tasks.py` — in-DB failure registry + re-run
