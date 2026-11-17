# Path 1: single-file change

- The poll loop, `MigrationLockTimeout(RuntimeError)` and `_lock_holder_pid` stay in `migrations/env.py`.
- `Settings.migration_lock_timeout_s` reuses `_positive("MIGRATION_LOCK_TIMEOUT_S", "300", float)`.
- `run_migrations_online` reads the deadline before `connect()`. Offline mode does not read it.
- Holder pid: `pg_locks` with `locktype='advisory'`, `granted`, `classid` = high 32 bits, `objid` = low 32 bits, `objsubid=1`.
- The `try/finally` release starts after the loop, so a timeout never calls `pg_advisory_unlock`.
- Tests: subprocess integration tests only, because env.py runs migrations on import.
- Effort: S, about 30 lines.
- Main risk: coverage and mutation gates do not measure subprocess runs.
