# Path 1: explicit dependency injection

## Core idea
`PostgreSQLStore` takes an optional frozen `PoolConfig(size, max_overflow)` through its constructor. Each caller picks the pool. The worker passes the worker pair. The Streamlit app uses the default, which is the app pair.

## Changed files
- `src/config/settings.py`: add a helper `_int_in_range(name, default, minimum)`. Add 4 properties (`db_pool_size`, `db_max_overflow`, `worker_db_pool_size`, `worker_db_max_overflow`). Add `app_pool_config()` and `worker_pool_config()`. Define `PoolConfig` here, because `postgres.py` already imports the settings.
- `src/plugins/relational_db/postgres.py`: `__init__` gets a keyword-only `pool: PoolConfig | None = None`. `initialize()` passes `pool_size` and `max_overflow` to `create_engine`. When `pool` is None, `initialize()` uses `app_pool_config()`.
- `src/tasks/fetch.py`: `_make_store()` builds `PostgreSQLStore(pool=get_settings().worker_pool_config())`.
- `src/ui/components/auth.py` and `src/bootstrap/init_stack.py`: no change.

## Contract
- `_int_in_range` returns an int. Unset or empty gives the default. A value that is not an integer raises `ValueError` and names the variable. A value below the minimum raises `ValueError` and names the variable. The minimum is 1 for the size and 0 for the overflow.
- `PoolConfig.__post_init__` checks `size >= 1` and `max_overflow >= 0`.
- `PostgreSQLStore.__init__` does not read the settings. `initialize()` raises `ValueError` before it builds the engine. The `SchemaNotAtHeadError` path does not change.

## Tests
- Settings: 4 variables x (default, override, rejected) = 12 cases or more. Exact boundaries for the mutation gate.
- The worker store engine has size 1 and overflow 1. The default store engine has size 5 and overflow 10.
- `_make_store` passes the worker pair.
- A bad value raises `ValueError` and leaves the store uninitialized.

## Effort
S. Four files. No dependency, no migration.

## Main risk
A new caller that builds `PostgreSQLStore()` in a worker gets the app pool. Mitigation: a test asserts that the worker uses `_make_store`.
