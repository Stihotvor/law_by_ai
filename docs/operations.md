# Operations

This page tells you how to run the Docker stack. Run all commands from the repository root.

Set this shortcut first:

```bash
COMPOSE="docker compose -f docker/docker-compose.yml"
```

## What runs

| Service | Purpose |
|---|---|
| `postgres` | Stores tenants, users and documents. |
| `redis` | Holds the Celery task queue. It runs Valkey and keeps no data on disk. A restart discards queued tasks and results. |
| `s3` | Stores document files (S3 API, SeaweedFS). |
| `init` | Runs once on each start. It prepares the schema, the bucket, the tenant and the first admin. |
| `app` | Serves the Streamlit web UI. |
| `celery-worker` | Runs background tasks, such as document fetch and OCR. |
| `test` | Runs the full test suite. It starts only with `--profile test`. |

## First start

1. Copy the example file and protect it:

    ```bash
    cp docker/.env.example docker/.env
    chmod 600 docker/.env
    ```

2. Replace every value that starts with `change-me`. Init stops with exit code 2 while `INIT_ADMIN_PASSWORD`, `POSTGRES_PASSWORD`, `MINIO_SECRET_KEY` or `REDIS_PASSWORD` still starts with `change-me`. Use letters and digits only in `MINIO_ACCESS_KEY` and `MINIO_SECRET_KEY`.
3. Start the stack and check it:

    ```bash
    $COMPOSE up -d --build
    $COMPOSE ps -a
    ```

4. Open the app on `http://127.0.0.1:8501`.

Init creates the schema, the bucket, the tenant and the first admin. It runs again on each `up`. A second run changes nothing.

The S3 service has no published port. Only the services on the backend network can reach it.

## Stop

```bash
$COMPOSE down
```

`down` removes the containers. It keeps the `pgdata` and `s3data` volumes, but it discards the queued tasks and results in `redis`, which keeps no data on disk.

!!! warning
    `down -v` deletes the `pgdata` and `s3data` volumes. All database rows and all stored files are lost. Make a dump first if you need the data.

```bash
$COMPOSE down -v
```

## Start again

```bash
$COMPOSE up -d
```

## Restart

- Restart all services: `$COMPOSE restart`.
- Restart one service: `$COMPOSE restart app`.

`restart` does not read `docker/.env` again. To apply a change to `docker/.env` or to the compose file, run `$COMPOSE up -d`. If a service does not change, run `$COMPOSE up -d --force-recreate <service>`.

## Rebuild

- Rebuild all images: `$COMPOSE up -d --build`.
- Rebuild the app and the worker only: `$COMPOSE up -d --build --no-deps app celery-worker`.
- Rebuild without the cache: `$COMPOSE build --no-cache`. Use it only to debug a stale layer. Each uncached build adds to the Docker build cache.
- Rebuild the test image: `$COMPOSE --profile test build test`. A stale test image runs old code.
- Before you apply a change to the `redis` image, pause producers, drain pending and active tasks, and save any results you still need. The broker keeps no data on disk, so the restart discards them.
- After a change to an image pin, pull the images, then start: `$COMPOSE pull`, then `$COMPOSE up -d`.

## Develop

1. Edit the code.
2. Rebuild the app and the worker: `$COMPOSE up -d --build --no-deps app celery-worker`.
3. Read the logs: `$COMPOSE logs -f app`.

Run the fast tests without Docker:

```bash
.venv/bin/pytest -m "not integration"
```

Run the full suite:

```bash
$COMPOSE --profile test run --rm test
```

Run one-off commands:

```bash
$COMPOSE run --rm init
$COMPOSE exec celery-worker celery -A tasks.celery_app inspect ping
```

## Run init again

```bash
$COMPOSE run --rm init
```

It is safe to repeat. Init checks the state first and creates only what is missing.

## Check health and resources

```bash
$COMPOSE ps
docker stats --no-stream
```

Measured limits:

| Service | Peak memory | Memory limit | CPUs | PIDs | Basis |
|---|---|---|---|---|---|
| `s3` | 377 MiB | 496m | 1.0 | 200 | One 50 MB multipart upload and download. |
| `celery-worker` | 229 MiB | 304m | 1.0 | 200 | The same upload, 10 pings. |
| `app` | 54 MiB | 256m | 1.0 | 200 | Provisional. One browser session only. |
| `postgres` | 58 MiB | 128m | 1.0 | 200 | Provisional. Light load only. |
| `redis` | 15 MiB | 32m | 0.5 | 100 | Provisional. Light load only. |
| `init` | not measured | 128m | 0.5 | 100 | Runs once and exits. |

Measured on 2026-11-05. No container was stopped for memory. The steady services add up to 1216 MiB, inside the 2 GiB budget. Re-measure the provisional rows with several sessions and a large database before you rely on them.

To find out if the kernel stopped a container because it used too much memory, run:

```bash
docker inspect -f '{{.State.OOMKilled}}' <container>
```

`true` means an out-of-memory kill. Increase the limit of that service.

## Change a password

A change to `POSTGRES_PASSWORD` in `docker/.env` does not change an existing database. Do one of these:

- Change the password in Postgres with `ALTER USER`, then update `docker/.env` and run `$COMPOSE up -d`.
- Delete the data with `$COMPOSE down -v`, then start again.

The S3 key pair comes from `docker/.env` on each start of the `s3` service. To change it, update `docker/.env` and run `$COMPOSE up -d`.

Init creates the first admin only once. A new `INIT_ADMIN_PASSWORD` does not change an existing admin. Change that password in the app.

## Upgrade to Postgres 18

The stack uses Postgres 18. Postgres 18 cannot open data from an older major version. The volume also mounts at `/var/lib/postgresql` now. If your `pgdata` volume has older data, do one of these:

- Delete the data with `$COMPOSE down -v`, then start again.
- Dump the data with the old stack (`pg_dump`). Start the new stack. Restore the dump (`psql` or `pg_restore`).

## Security facts

- Published ports bind to `127.0.0.1` only.
- The backend network has no internet access. Only `app` and `celery-worker` also join the edge network.
- Containers run as non-root users with all Linux capabilities dropped.
- The S3 service runs as UID 1000. This UID owns `/data` in the image.
- SeaweedFS telemetry is off (`-master.telemetry=false`). Keep it off.
- OCR is off by default. When `OCR_ENABLED=true`, document content goes to the Mistral service.
- All services use one S3 key pair with admin rights until a scoped key exists.
- Keep `docker/.env` at mode 600. It holds every secret of the stack.

## Restart limits

After a host reboot, Docker restarts the containers. It does not wait for the health order. The app and the worker retry their connections. If a service stays unhealthy, run `$COMPOSE up -d`.

## Troubleshooting

Init exit codes:

| Code | Meaning | Action |
|---|---|---|
| 0 | All steps are done or were done before | None |
| 2 | The configuration is not valid | Read the log. Fix `docker/.env`. |
| 3 | Postgres or S3 did not answer after 5 tries of a step | Check `$COMPOSE ps` and the service logs. |
| 4 | A step failed | Read the log line with `result=failed`. |

`required variable ... is missing a value`: Compose found an empty required variable. Set it in `docker/.env`.

`Read-only file system`: the container root is read-only. The service writes only to `/tmp` or to its volume. Add a `tmpfs` entry for the path in the log, and write the reason as a comment next to it.
