# Decision: migration lock deadline

## Context
The online Alembic run takes `pg_advisory_lock` on key `0x6C61775F6D6967` with no time limit. The DBA review and the security review of the run-once change rated this medium. Requirements are in `requirements.md`. Size S, so two lenses were compared.

## Options
- Path 1: keep the poll loop in `migrations/env.py`. Effort S. Only subprocess tests reach the loop.
- Path 2: move the lock into `src/storage/advisory_lock.py` with an injectable clock and sleep. Effort S-M. Unit tests reach the loop without a database.

| Row | Path 1 | Path 2 |
|---|---|---|
| Fit to constraints | All met | All met |
| Failure modes | All listed, holder race only as "unknown" | All listed, each one unit-tested |
| Complexity | Low, one file | Low, one new module |
| Effort | S | S-M |
| Main risk | Coverage and mutation gates do not see the loop | Wrong `pg_locks` key split |

## Decision
Path 2, chosen by the owner on 2026-11-17.
- The coverage and mutation gates of CONTRIBUTING.md can measure the lock logic.
- Fake clock and sleep make the 1 s poll and the deadline testable without delays.
- `env.py` stays a thin Alembic entry point.

## Consequences
- The diff is larger than Path 1, about 80 lines plus tests.
- `migrations/env.py` imports `storage.advisory_lock`.
- The integration test must assert the real holder pid to guard the `classid`/`objid` split.
- `docs/migrations.md`, section "Overlapping upgrade runs", describes the deadline, the setting and the error.
