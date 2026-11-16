# Path 2: single migration entry point outside Alembic

- New `src/bootstrap/migrate.py` with `upgrade_locked(url)` and `main()` for `python -m bootstrap.migrate`.
- It opens a separate AUTOCOMMIT NullPool connection, takes `pg_advisory_lock`, calls `alembic.command.upgrade(cfg, "head")`, and unlocks and closes in `finally`.
- `docker/docker-compose.yml` `init` and `test` commands and `init_stack.alembic_upgrade` call it. `migrations/env.py` stays as it is.
- Failures: same as path 1. Closing the lock connection frees the lock even if the unlock fails.
- Tests: two concurrent `python -m bootstrap.migrate` subprocesses on an empty scratch database; one run at head leaves no lock. Unit test for the unlock order with a fake connection.
- Risks: the plain `alembic upgrade head` CLI skips the lock (operator runs, the hint in `schema_check.py`). Two connections: if the lock connection drops, the lock is lost during the migration. It conflicts with requirements.md (no change to `init`).
- Effort: S, but compose edits need a Docker suite run.
