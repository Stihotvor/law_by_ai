# Decision: migration run once

## Context
The one-shot `init` service already runs `alembic upgrade head` before the app and the worker start, and the stores only check the schema head. Two upgrade runs can still overlap: an operator by hand, a second stack, or the `test` service. Overlapping runs fail with "already exists" errors.

## Options
- Path 1: a session-level `pg_advisory_lock` in `migrations/env.py`, on the same connection as the DDL. It covers every caller.
- Path 2: a `bootstrap.migrate` wrapper with the lock on a second connection. It changes `init`, and the plain `alembic` CLI skips the lock.

## Decision
Path 1. The architect and the DBA both found it feasible and recommended it. Both rejected path 2.
- Lock key: a fixed literal bigint constant `0x6C61775F6D6967` ("law_mig"). Do not compute the key with `hashtext()`. The tests copy the literal, because an import of `env.py` runs the migrations. The blocking test fails if the two keys differ.
- Order: take the lock, commit to end the autobegin transaction, then `context.configure` and `begin_transaction` / `run_migrations`.
- `finally`: roll back an open transaction, then unlock and commit. A try/except logs an unlock error, so it cannot hide the original error. NullPool closes the session, which frees the lock anyway.
- Use a session lock, never `pg_advisory_xact_lock`.
- Offline mode takes no lock.

## Consequences
- One file of product code changes. `init`, the stores and the schema stay as they are.
- `migrations/` is outside coverage and mutation scope. Four Docker integration tests are the proof: concurrent runs, deterministic blocking, a failed upgrade that frees the key, and offline mode with the key held.
- A run waits with no limit while another run holds the lock. A future `lock_timeout` would make the waiting run fail.

## Review warnings kept
- No lock timeout (perf and security, medium). The requirements accept an unlimited wait. Any role can take the key, but that needs SQL access to the database first. A deadline with `pg_try_advisory_lock` is a possible follow-up.
- No test proves that the `finally` unlock runs. A subprocess frees the lock when it exits, so a test cannot see the difference. The failed-upgrade test proves that the error is not hidden and that the key is free afterwards. For the same reason, the "no lock left at head" test was dropped.
- The test copies the lock key (style). An import of `env.py` runs the migrations. The blocking test fails if the keys differ.
- The offline test runs only to the first revision. A later migration reads data, which `--sql` mode cannot do (this was true before this change).
- Style items 3, 6 and 7 (repeated key dict, "Scenario:" docstrings, inline unlock in the tests) stay as they are. They are small and readable.
