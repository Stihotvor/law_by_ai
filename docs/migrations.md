# Database Migrations

PostgreSQL schema is managed with **Alembic** (issue #9). Models live in
`plugins/relational_db/postgres.py` (`Base.metadata`); migration scripts live
in `migrations/versions/`. The migration environment reads the database URL
from `config.settings` (`POSTGRES_URL` or `POSTGRES_*`), so it matches how the
application connects.

## Commands

Run through **uv** (the project's package manager):

| Task                                            | Command                                                          |
|-------------------------------------------------|------------------------------------------------------------------|
| Apply all pending migrations                    | `uv run alembic upgrade head`                                      |
| Apply up to a specific revision                 | `uv run alembic upgrade <rev>`                                     |
| Undo the last migration                         | `uv run alembic downgrade -1`                                      |
| Undo to a specific revision                     | `uv run alembic downgrade <rev>`                                   |
| Create a migration from model changes           | `uv run alembic revision --autogenerate -m "describe change"`      |
| Create an empty migration (manual SQL)          | `uv run alembic revision -m "describe change"`                     |
| Show the current revision                       | `uv run alembic current`                                           |
| Show migration history                          | `uv run alembic history`                                           |
| Show heads (tip revisions)                      | `uv run alembic heads`                                             |
| Stamp an existing DB as up-to-date (no SQL)     | `uv run alembic stamp head`                                        |

## Workflow

1. Change the ORM models in `plugins/relational_db/postgres.py`.
2. Generate a migration: `uv run alembic revision --autogenerate -m "what changed"`.
3. Review the generated file in `migrations/versions/` — autogenerate can miss
   column-level changes.
4. Apply it: `uv run alembic upgrade head`.

> **Note:** autogenerate compares against the live database, so run it against
> a schema that is at the latest revision (`upgrade head` first).

## Migrations in the data store

`PostgreSQLStore.initialize()` runs `alembic upgrade head` automatically before
serving, so the app always brings its schema up to date on startup. RLS
policies for `users`/`tenants` live in the migrations (ADR-0003).

## Docker / test compose

The `test` compose profile (`docker compose --profile test -f
docker/docker-compose.yml run --rm test`) boots a fresh PostgreSQL volume;
`PostgreSQLStore.initialize()` applies the migrations before integration tests
run.

Existing local databases created before Alembic (tables created via
`create_all`) can be adopted with `uv run alembic stamp head` once the schema
matches the initial migration.
