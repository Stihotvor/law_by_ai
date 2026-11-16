# Requirements: worker DB pool size

## Business Goals
- The stack runs on a host with 4-6 GB RAM. Each PostgreSQL connection costs memory on the server.
- Today one Celery worker with `--concurrency=2` can open up to 30 connections (2 children x (5 + 10)). Streamlit adds up to 15 more.
- Goal: the worker opens at most 4 connections (2 children x (1 + 1)). The Streamlit app keeps a pool size that the operator can set.

## Technical Constraints
- Python 3.13, SQLAlchemy 2.x `create_engine` with the default `QueuePool`.
- `PostgreSQLStore.initialize()` builds the engine from `get_settings()`. Settings are `os.getenv` properties on `Settings`.
- The worker builds its store lazily inside a task, after fork (`src/tasks/fetch.py`). No engine exists in the parent before fork.
- The new settings: `POSTGRES_POOL_SIZE` (default 5), `POSTGRES_MAX_OVERFLOW` (default 10), `WORKER_POSTGRES_POOL_SIZE` (default 1), `WORKER_POSTGRES_MAX_OVERFLOW` (default 1).
- No new dependency. No migration. The architecture does not change.

## Edge Cases
- `pool_size=0` makes a `QueuePool` unlimited in SQLAlchemy 2.x. The settings must reject a value lower than 1.
- SQLAlchemy documents `max_overflow=-1` as no overflow limit. The settings must reject a value lower than 0, so the pool is never unlimited.
- A value that is not an integer (for example `"abc"`) must raise a clear `ValueError` that names the variable.
- An empty or unset variable uses the default.

## Failure Modes
- A bad pool value fails at engine build time with a `ValueError` that names the variable. It never falls back silently to an unlimited pool.
- When all worker connections are busy, a task waits for the pool timeout (30 s default) and then fails. The failed task is persisted by the existing failure path (ADR-0006).
- The Streamlit app is not affected by the worker settings.

## Success Metrics
- The worker engine has `pool.size() == 1` and an overflow of 1 with the default settings: 1 unit test.
- The app engine has `pool.size() == 5` and an overflow of 10 with the default settings: 1 unit test.
- Each of the 4 settings has a test for the default, a valid override and a rejected value: at least 12 cases.
- With `--concurrency=2`, the worker opens at most 4 connections (down from 30).
- Gate: ruff, pyright, fast tests, diff-cover 90% or more on the changed lines, Docker suite, CI mutation gate.
