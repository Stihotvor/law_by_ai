# worker-189 decision

## Context
The worker lifecycle issue asked workers to migrate once and close the store on exit. The RLS hardening change already moved migrations to the compose `init` service (`lawbyai_owner`). Workers only check the schema head. The open gap: no code closes the per-child `PostgreSQLStore` in `src/tasks/fetch.py`, and a comment there still says the store migrates.

## Options
- P1 local handler: module-level `_store` and a `worker_process_shutdown` handler in `fetch.py`. Effort S.
- P2 central registry: `src/tasks/lifecycle.py` with `close_all()` wired in `celery_app.py`. Effort M.
- P3 Celery Task base class: lazy `store` property and `close_store()`, `bind=True`. Effort S.
- P4 storage provider: `get_store()` / `close_store()` in `postgres.py`. Effort S-M.

## Decision
P1, chosen by the user.
- `fetch.py` replaces `functools.cache` with a module-level `_store: PostgreSQLStore | None`. `_make_store()` builds it lazily inside a task.
- `_close_store(**_: object)` is connected to `worker_process_shutdown`. Empty cache: return, build nothing. Else call `close()` once, log a warning with `exc_info` on error, clear `_store` in `finally`.
- The stale migration comment is corrected. No migration, role or `celery_app.py` change.
- A failed build (for example `SchemaNotAtHeadError`) leaves `_store` as `None`, so the next task tries again (dba review).
- Tests: 6 unit tests (no DB, no network) and 1 integration test on live PostgreSQL. The integration test saves `old_pool = store._engine.pool` after one query, asserts `old_pool.checkedin() > 0`, sends the signal, then asserts `old_pool.checkedin() == 0`, `store._engine is None` and `_store is None` (architect review: `checkedout() == 0` cannot fail).
- Handler signature `_close_store(**_: object)` with `global _store`. Unit tests reset `_store` in an autouse fixture.

## Consequences
- Smallest diff: one source file. No change to the `fetch_document` signature.
- The signal fires only in prefork children (also on `max_tasks_per_child` recycle). The solo pool, the threads pool and eager mode never fire it. Celery does not guarantee it, and a cold shutdown or hard kill can skip or cut it. Process exit then frees the sockets. Accepted risk.
- A future task module with its own store needs its own handler. Extract a shared provider (P4) when a second consumer exists.
- The dba review is light: no schema, migration or role change.
- The worker lifecycle issue text must be updated to drop the migration scope.
