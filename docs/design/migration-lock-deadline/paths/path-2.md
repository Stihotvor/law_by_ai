# Path 2: extracted lock module

- New module `src/storage/advisory_lock.py`: context manager `advisory_lock(connection, key, timeout_s, *, clock=time.monotonic, sleep=time.sleep, poll_s=1.0)`.
- `AdvisoryLockTimeout(RuntimeError)` with `key`, `timeout_s`, `holder_pid: int | None`. The message names the key in hex, the deadline, and the pid or "unknown".
- Loop: try `pg_try_advisory_lock`, end the transaction after each try, log one wait line on the first failure, sleep `poll_s`, stop at the deadline.
- On the deadline: query the holder in `pg_locks` (key split into `classid`/`objid`, `objsubid=1`), then raise. The body never runs.
- A database error in a poll or in the `pg_locks` query propagates unchanged.
- Release keeps the current behaviour: log a failure, do not raise.
- `Settings.migration_lock_timeout_s` reuses `_positive("MIGRATION_LOCK_TIMEOUT_S", "300", float)`.
- `migrations/env.py` keeps `MIGRATION_LOCK_KEY`, reads the deadline before `connect()`, and calls the module.
- Tests: unit tests with a fake connection, clock and sleep. One subprocess integration test with a held key.
- Effort: S-M, about 80 lines.
- Main risk: a wrong `classid`/`objid` split gives "unknown". The integration test asserts the real pid.
