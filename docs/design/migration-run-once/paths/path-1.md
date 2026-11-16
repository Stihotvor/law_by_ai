# Path 1: in-process lock in the migration environment

- Only `run_migrations_online()` in `migrations/env.py` changes. Offline mode, `init`, the stores and the schema stay as they are.
- A module constant `_MIGRATION_LOCK_KEY` (a fixed bigint) and a context manager `_advisory_lock(connection)`.
- Order: open the connection (NullPool), run `SELECT pg_advisory_lock(:key)`, commit to end the autobegin transaction, then `context.configure` and `begin_transaction` / `run_migrations` inside `try`.
- `finally`: roll back an open transaction, run `pg_advisory_unlock`, commit.
- Session-level lock on the same connection as the DDL, so one session holds it for the whole run. A waiting run reads `alembic_version` only after it holds the lock, sees head and does nothing.
- Failures: a failed migration rolls back, unlocks and re-raises. A dead process frees the lock with its session. No lock timeout (accepted).
- Tests: two concurrent `alembic upgrade head` subprocesses on an empty scratch database (both exit 0, 1 row at head); one run at head leaves no advisory lock in `pg_locks`.
- Risks: transaction order with the pinned Alembic version; the race test can pass by luck without the lock; pyright typing.
- Effort: S. About 20 lines in one file plus 2 integration tests. Covers every caller: `init`, the operator CLI, the `test` service.
