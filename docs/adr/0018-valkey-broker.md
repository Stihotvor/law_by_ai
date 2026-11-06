---
status: accepted
---

# ADR-0018: Valkey as the Celery broker and result store

## Context

The stack uses Redis only as the Celery broker and result store (ADR-0006). No
data is kept on disk. The compose service runs `redis:8.8.4-alpine`.

The goal is to avoid license risk now and in the future. Redis 8 is offered
under a choice of three licenses: RSALv2, SSPLv1, or AGPLv3 (source: the Redis
licensing page, https://redis.io/legal/licenses/). RSALv2 and SSPLv1 are
source-available licenses and are not approved by the OSI. AGPLv3 is an open
source license with network copyleft.

The project does not change Redis and runs it as a separate service, so this
ADR does not claim a proven conflict with the MIT license today. The risk is
for the future. A self-hosting operator who changes or offers Redis as a
service can fall under these terms, and the project cannot give a clear
answer. This is not legal advice. Redis has changed its license once already,
and the vendor can change it again.
Valkey is the BSD-3-Clause fork of Redis 7.2. It is developed under the Linux
Foundation, not by one vendor. It speaks the same protocol.

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
- **Redis 7.2.x** - rejected. Redis lists the 7.2.x series as BSD-3-Clause and
  as supported for security fixes, so it is valid today. It does not remove
  the license risk. It is the last BSD line from Redis, it gets no new
  features, and the vendor controls the license of every later version. The
  project would have to leave Redis later anyway. Valkey removes the risk
  now. The end date of 7.2 support was not verified.
- **Postgres-based queue** - rejected. Celery has no stable Postgres broker,
  and it adds load on the database.
- **KeyDB, Dragonfly** - not tested. Not needed, because Valkey passed.

## Related

- ADR-0006 (Celery and Redis)
