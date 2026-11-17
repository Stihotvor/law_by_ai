# Requirements: migration lock deadline

## Business Goals
- An operator who runs `alembic upgrade head` gets a clear failure within a known time when another session holds the migration lock. Today the run waits with no limit.
- This closes the medium finding of the DBA review and the security review of the run-once change: a hung run, or any role that takes the key `0x6C61775F6D6967`, blocks every later upgrade.

## Technical Constraints
- PostgreSQL session advisory lock, key `0x6C61775F6D6967`, taken in `migrations/env.py` (online mode only).
- The run polls `pg_try_advisory_lock` every 1 s until the deadline. It does not use `pg_advisory_lock` with `lock_timeout`.
- The deadline is a typed property in `src/config/settings.py`, read from the environment variable `MIGRATION_LOCK_TIMEOUT_S`. Default: 300 s.
- The value must be a positive number. A non-numeric or non-positive value fails at start with an error that names the variable.
- No new dependency. Python 3.13, SQLAlchemy, Alembic.

## Edge Cases
- The lock is free: the first try succeeds, the run logs no wait line, and migrations run as today.
- The lock is held and is freed before the deadline: the run takes the lock at the next poll and applies only the missing revisions.
- The lock is held past the deadline: the run fails. It applies no revision, and `alembic_version` is unchanged.
- The holder ended between the last try and the `pg_locks` query: the error says the holder is unknown.
- `MIGRATION_LOCK_TIMEOUT_S` is `0`, `-5` or `abc`: the run fails before it connects.
- Offline mode (`--sql`) takes no lock and reads no deadline.

## Failure Modes
- On timeout the run raises an error (a `RuntimeError` subclass). The message names the key `0x6C61775F6D6967`, the deadline in seconds, and the holder backend pid from `pg_locks`, or "unknown".
- The process exits non-zero, so the one-shot `init` service fails and dependent services do not start.
- When the first try fails, the run logs one line: it waits for the key, with the deadline.
- A failed poll query (connection lost) raises the database error. It is not reported as a timeout.

## Success Metrics
- An integration test holds the key on a second connection, sets the deadline to 2 s, and checks that the run fails in 2 s to 5 s with the key and the holder pid in the message.
- The same test checks that `alembic_version` has 0 changed rows.
- 3 of the 4 existing tests in `tests/integration/test_migration_lock.py` pass unchanged. `test_upgrade_blocks_while_lock_held` detects the wait from the wait log line or a still-running process, because polling leaves no not-granted row in `pg_locks`.
- Unit tests cover the setting: default 300, valid value, and 3 invalid values (`0`, `-5`, `abc`).
- Quality gate: ruff check, ruff format --check, pyright and pytest all pass. Coverage and mutation gates of CONTRIBUTING.md pass.
