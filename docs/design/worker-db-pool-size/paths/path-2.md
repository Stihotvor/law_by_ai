# Path 2: environment-driven process role

## Core idea
`PostgreSQLStore` keeps its no-argument constructor. `initialize()` reads the pool values from the settings. A new `PROCESS_ROLE` setting (`app` or `worker`) selects the pair. Compose sets `PROCESS_ROLE=worker` only on the `celery-worker` service.

## Changed files
- `src/config/settings.py`: 4 int properties (`DB_POOL_SIZE` 5, `DB_MAX_OVERFLOW` 10, `WORKER_DB_POOL_SIZE` 1, `WORKER_DB_MAX_OVERFLOW` 1), one int-parse helper, and a `process_role` property (default `app`).
- `src/plugins/relational_db/postgres.py`: `initialize()` picks the pair by role and passes it to `create_engine`.
- `docker/docker-compose.yml`: the `celery-worker` service gets `PROCESS_ROLE=worker` and passes the `WORKER_*` variables.
- `src/tasks/fetch.py`: no change.

## Contract
- Each int property returns an int. Unset or empty gives the default. A value that is not an integer, a size below 1 or an overflow below 0 raises `ValueError` and names the variable.
- `process_role` returns `app` or `worker`. Any other value raises `ValueError` that names `PROCESS_ROLE`.
- `initialize()` keeps its signature. It raises `ValueError` before it builds the engine.

## Tests
- Settings: 12 cases or more, plus the role values.
- Store engine with the default role: size 5, overflow 10. With `PROCESS_ROLE=worker`: size 1, overflow 1.
- A compose check that `celery-worker` carries the worker role.

## Effort
S. Three files plus compose.

## Main risk
The role is a deploy-time contract. A worker that starts without `PROCESS_ROLE=worker` (another compose file, a manual `celery` run) gets 5+10 again, and no code detects it. It also adds a fifth setting that the requirements do not list.
