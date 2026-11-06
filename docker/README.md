# Docker

Containers and orchestration. The operations page in the docs has the full run guide.

- `Dockerfile`: pinned `python:3.13` slim base, multi-stage uv build (`builder`, `base`,
  `runtime`, `test`), non-root user (UID 10001). Dev extras (pytest, etc.) are
  installed only in the `test` target, never in `runtime`.
- `docker-compose.yml`: services `postgres`, `redis`, `s3` (SeaweedFS), `init`
  (one-shot setup), `app` (Streamlit), `celery-worker`, and `test`.
  - Every long-running service has a healthcheck, memory and CPU limits, a
    read-only root, no Linux capabilities and a non-root user.
  - `backend` is an internal network with no internet. `edge` carries the
    published app port and the worker's outbound calls.
  - Volumes: `pgdata` (Postgres) and `s3data` (S3 files).
  - The `test` service is gated behind `profiles: ["test"]`: a plain
    `docker compose up` never builds or starts it.
- `.env.example`: the template for `docker/.env`. Compose reads it to fill
  `${...}` values. Each service gets only the variables in its `environment:`
  block. Only `test` loads the whole file.
- `.env`: your local, gitignored copy. Run `chmod 600 docker/.env`.

Run the stack:

```bash
cp docker/.env.example docker/.env   # once, then replace every change-me value
chmod 600 docker/.env
docker compose -f docker/docker-compose.yml up -d --build
```

Run the test suite against live postgres and redis (builds the `test` target,
starts only postgres and redis):

```bash
docker compose --profile test -f docker/docker-compose.yml run --rm test
```
