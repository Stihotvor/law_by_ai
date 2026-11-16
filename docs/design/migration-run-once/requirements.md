# Requirements: migration run once

## Business Goals
- The one-shot `init` service already runs `alembic upgrade head` before the app and the worker start. Stores only check the schema head.
- A second `alembic upgrade head` can still start at the same time: an operator by hand, a second stack on the same database, or the `test` service next to `init`.
- Goal: concurrent upgrade runs apply each migration once. No run crashes with "already exists" errors.

## Technical Constraints
- Python 3.13, Alembic, SQLAlchemy 2.x, PostgreSQL. The lock lives in `migrations/env.py`, online mode only.
- The owner role `lawbyai_owner` runs migrations. It can call `pg_advisory_lock` (no extra grant needed).
- No new migration, no schema change, no new dependency. No change to `init` or to the stores.
- Offline mode (`--sql`) has no connection and takes no lock.

## Edge Cases
- Empty database: the first run creates `alembic_version`. The second run waits, then sees head and does nothing.
- Database already at head: the run takes the lock, does nothing, and releases the lock.
- A third concurrent run: it waits like the second one.

## Failure Modes
- A migration fails: the run rolls back its transaction, releases the lock and re-raises. The waiting run then takes the lock and tries again from the same revision.
- A process dies while it holds the lock: PostgreSQL ends the session and frees the session-level lock.
- A run waits with no time limit while another run holds the lock. This is accepted: migrations are short, and a hung run is visible in `pg_locks`.
- If a role or the server later sets `lock_timeout` or `statement_timeout`, the waiting run fails with a timeout error. No timeout is set today.

## Success Metrics
- 2 concurrent `alembic upgrade head` processes on an empty scratch database: both exit 0, and `alembic_version` holds exactly 1 row equal to head. 1 integration test.
- While one session holds the lock key, a second `alembic upgrade head` is still running after 2 s and exits 0 after the lock is released: 1 integration test.
- A run on a database at head exits 0 and leaves no advisory lock in `pg_locks`: 1 integration test.
- Gate: ruff, ruff format, pyright, fast tests, Docker suite, CI mutation gate. 0 failures.
