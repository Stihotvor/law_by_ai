# Decision: worker DB pool size

## Context
`PostgreSQLStore.initialize()` builds its engine with the default `QueuePool` (5 + 10). Each Celery prefork child caches its own store. With `--concurrency=2`, the worker can open 30 connections. The stack must fit in 4-6 GB RAM. See `requirements.md`.

## Options
- Path 1: the caller passes a `PoolConfig` to `PostgreSQLStore`. The worker passes 1 + 1. The app uses the default 5 + 10.
- Path 2: a `PROCESS_ROLE` setting selects the pool inside the store. Compose sets the worker role.

## Decision
Path 1, chosen by the owner at the design gate. The solution architect and the DBA reviewed both paths and prefer Path 1.

Design points from the reviews:
1. `src/config/settings.py`: add one helper `_int_at_least(name, default, minimum)`. An unset or empty value gives the default. A value that is not an integer, or that is below the minimum, raises `ValueError` and names the variable. The existing `_positive` helper stays as it is: it also parses floats and has 9 callers, and a change to it is outside this issue.
2. `src/config/settings.py`: add a frozen dataclass `PoolConfig(size, max_overflow)`. `__post_init__` raises `ValueError` when `size < 1` or `max_overflow < 0`. Add the properties `postgres_pool_size` (default 5), `postgres_max_overflow` (default 10), `worker_postgres_pool_size` (default 1) and `worker_postgres_max_overflow` (default 1). Add `app_pool_config()` and `worker_pool_config()`.
3. `src/plugins/relational_db/postgres.py`: `PostgreSQLStore.__init__` gets a keyword-only `pool: PoolConfig | None = None` and does not read the settings. `initialize()` uses `pool`, or `get_settings().app_pool_config()` when it is None. It calls `create_engine(url, future=True, pool_size=..., max_overflow=..., pool_pre_ping=True, pool_timeout=30)`.
4. `src/tasks/fetch.py`: `_make_store()` builds `PostgreSQLStore(pool=get_settings().worker_pool_config())`.
5. `docker/docker-compose.yml`: pass `POSTGRES_POOL_SIZE` and `POSTGRES_MAX_OVERFLOW` in `x-app-env`. Pass `WORKER_POSTGRES_POOL_SIZE` and `WORKER_POSTGRES_MAX_OVERFLOW` on `celery-worker`. Add the four variables to `docker/.env.example`.

6. The `_int_at_least` docstring states that an empty value gives the default, unlike `_positive`, which raises on an empty value. Both behaviors are intended.
7. Add the four variables to the variable table in the `settings.py` module docstring. Export `PoolConfig` in `__all__`.
8. Compose uses bare keys (`NAME:`). `docker/.env.example` lists the four variables commented out with their defaults. `x-app-env` also goes to `celery-worker` and `test`, so the worker sees the app values too. This is harmless, because the worker reads only the `WORKER_*` pair. `init` uses only `x-db-env`, so it gets the code defaults.
9. In `initialize()`, the pool config is resolved before `create_engine` is called.
10. The only store builder in `src/tasks` is `_make_store` (checked with grep: other builders are only in `src/ui/components/auth.py` and `src/bootstrap/init_stack.py`). One integration test runs `fetch_document` with a 1 + 1 pool.

## Contract
- `Settings.worker_pool_config()` and `Settings.app_pool_config()`: no input. They return a `PoolConfig`. They raise `ValueError` that names the variable.
- `PoolConfig(size: int, max_overflow: int)`: raises `ValueError` for `size < 1` or `max_overflow < 0`.
- `PostgreSQLStore(on_document_deleted=None, *, pool=None)`: never raises for the pool.
- `PostgreSQLStore.initialize()`: for the app store, a bad setting raises `ValueError` before any engine exists. `SchemaNotAtHeadError` behavior does not change.
- `_make_store()`: a bad `WORKER_*` value raises `ValueError` here, before `initialize()`. `_store` stays None, so the next task tries again.

## Consequences
- The worker opens at most 4 connections with `--concurrency=2` (was 30).
- `pool_pre_ping` adds one round trip on each checkout. A worker child then survives a Postgres restart.
- The `init` bootstrap service uses the app pool. It is short-lived, so this is accepted.
- Risk: a new worker caller that builds `PostgreSQLStore()` directly gets the app pool. A test asserts that the fetch task gets its store only from `_make_store`.
- Not in scope (follow-up): lower the app default (about 3 + 2) and tune Postgres memory (`max_connections` about 30, `shared_buffers` about 32 MB) for the 128 MB container limit.
