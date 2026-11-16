# worker-189 requirements

## Business Goals
- Each Celery worker child releases its PostgreSQL connections when it exits, so restarts and autoscale do not leave idle connections on a 4-6 GB host.
- The code and comments match the RLS hardening change: workers never migrate. The `init` service runs `alembic upgrade head` as `lawbyai_owner`.
- Decided: migration work is dropped from the worker lifecycle issue. The issue text is updated to say the RLS hardening change delivered it.

## Technical Constraints
- Python 3.13, Celery prefork pool, SQLAlchemy engine inside `PostgreSQLStore`.
- The store stays lazy: `_make_store` runs only inside a task, never at import time or in the parent process.
- Close uses the Celery `worker_process_shutdown` signal only. No `atexit` fallback (user decision).
- Files: `src/tasks/fetch.py` (and `src/tasks/celery_app.py` only if the handler belongs there). No migration or role change.
- Quality gate: ruff, pyright, `pytest -m "not integration"`, diff-cover 90%, Docker suite, mutation gate.

## Edge Cases
- A child that never ran a task has no cached store: the handler creates no `PostgreSQLStore` and opens no connection.
- A child that ran many tasks has one store: the handler calls `close()` once.
- After close, the cache is cleared, so a later call in the same process builds a new store, not a closed one.

## Failure Modes
- `store.close()` raises: the handler logs a warning with the traceback and returns. The child exits normally.
- Celery skips the signal (hard kill, crash): process exit frees the sockets. Accepted risk, documented.
- Schema behind head: unchanged; `initialize()` raises `SchemaNotAtHeadError` on first task.

## Success Metrics
- 100% of unit tests for the handler pass with no database and no network.
- 1 integration test on live PostgreSQL: after the handler runs, the saved old pool goes from more than 0 checked-in connections to 0, the store engine is None and the cache is empty.
- 0 calls to `PostgreSQLStore()` when the handler runs in a child with no store.
- 1 call to `close()` per child that has a store.
- diff-cover >= 90% on changed lines. Mutation score meets the CONTRIBUTING.md gate.
