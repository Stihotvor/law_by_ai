---
status: proposed
---

# ADR-0018: Valkey as the Celery broker and result store

## Context

The stack uses Redis only as the Celery broker and result store (ADR-0006). No
data is kept on disk. The compose service runs `redis:8.8.4-alpine`.

Redis 8 has a license problem for a public MIT project. It is offered under
RSALv2, SSPLv1, or AGPLv3. Valkey is the BSD-3-Clause fork of Redis 7.2. It
speaks the same protocol.

### Spike

The maintainer ran one spike on 2026-11-06 on the dev host (Docker 28.5.1).

- Image: `valkey/valkey:8-alpine` (Valkey 8.1.11, amd64, 42 MB).
- Container: same hardening as the `redis` service. It has a read-only root,
  `cap_drop: ALL`, `no-new-privileges`, user `999:999`, a tmpfs `/data`, 32 MB
  RAM, 0.5 CPU, and 100 PIDs.
- Command: `valkey-server --requirepass "$REDIS_PASSWORD" --save "" --appendonly no`.
- Client: Celery 5.6.3 and `redis` 6.4.0 from the project venv, with a worker
  on the host (`-P solo`).

Results:

| Check | Result |
|-------|--------|
| Container starts with the hardening above | Pass |
| `redis-cli ping` and `valkey-cli ping` with `REDISCLI_AUTH` | `PONG` (both CLIs ship) |
| `valkey-cli ping` without a password | `NOAUTH Authentication required` |
| `redis` Python client without a password | `AuthenticationError` |
| `celery inspect ping` | `pong`, 1 node online |
| Task `add(2, 3)` through broker and result backend | Result `5` |
| Memory after the test | 4.1 MiB of 32 MiB |

The image has no default user (it runs as root), so compose must set
`user: "999:999"`. The spike did this and Valkey started with the tmpfs `/data`.

## Decision

1. **Valkey replaces Redis 8 as the broker and result store.** The license is
   BSD-3-Clause.
2. **The clients stay.** Celery and the Python `redis` client do not change.
   The env names `REDIS_PASSWORD` and the `redis://` URLs keep their names.
3. **Only the compose service changes.** Pin the image by tag and by digest.

## Not verified

- A full run of the project stack and the compose tests on Valkey.
- Behaviour under load, and long-running tasks with retries.
- The image architectures other than amd64.
- Whether the image is a Docker Official Image or a publisher image.
- A vulnerability scan of the image.
- How Dependabot handles an image pinned by tag and digest.
- Celery does not list Valkey as a supported broker. The spike shows that it
  works. A future Valkey change could break it.

## Consequences

- Change the `redis` service in `docker/docker-compose.yml`: image, command
  (`valkey-server`), and healthcheck (`valkey-cli ping`).
- Set `user: "999:999"` explicitly.
- Update `docs/operations.md`, `docker/README.md`, and the compose tests.
- Keep the service name `redis` for now. A rename is a separate decision.
- Plan the cutover. The broker keeps no data on disk, so a restart or the
  switch from Redis to Valkey discards queued tasks and stored results. Before
  the switch, pause producers, drain pending and active tasks, and save any
  result that is still needed.
- Revisit this decision if a Celery release breaks on Valkey, or if Redis
  returns to a permissive license.

## Alternatives Considered

- **Keep Redis 8** - rejected. The license is RSALv2, SSPLv1, or AGPLv3.
- **Redis 7.2 or older** - rejected. Only 7.2.4 and older are BSD-licensed, and
  these versions no longer get fixes. The license of later 7.2 patch releases
  was not verified.
- **Postgres-based queue** - rejected. Celery has no stable Postgres broker,
  and it adds load on the database.
- **KeyDB, Dragonfly** - not tested. Not needed, because Valkey passed.

## Related

- ADR-0006 (Celery and Redis)
