# Database Migrations

PostgreSQL schema is managed with **Alembic**. Models live in
`plugins/relational_db/postgres.py` (`Base.metadata`); migration scripts live
in `migrations/versions/`. The migration environment reads the owner database
URL from `config.settings` (`POSTGRES_OWNER_URL`, or `LAWBYAI_OWNER_PASSWORD`
and `POSTGRES_*`).

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

The app does not apply migrations on startup. `PostgreSQLStore.initialize()`
only reads the revision of the database. If the revision is not the head
revision, it raises `SchemaNotAtHeadError`.

Migrations run with the owner connection (`POSTGRES_OWNER_URL`, user
`lawbyai_owner`). The app role (`POSTGRES_URL`, user `lawbyai_app`) cannot
change the schema. RLS policies for `users`/`tenants` live in the migrations
(ADR-0003).

## Docker / test compose

The `init` service runs `alembic upgrade head` with the owner connection, then
runs the bootstrap program. Start it before the app services.

The `test` service runs `alembic upgrade head` with the owner connection, then
runs the tests. The tests truncate tables. Run them in a separate Compose
project, so that they use their own volume and not the `pgdata` volume of your
normal stack:

```bash
docker compose -p law-by-ai-test --profile test -f docker/docker-compose.yml run --rm test
docker compose -p law-by-ai-test --profile test -f docker/docker-compose.yml down -v
```

Existing local databases created before Alembic (tables created via
`create_all`) usually hold only local test data. Prefer a fresh volume for
them. `create_all` does not create the RLS policies of the initial migration,
and the later revisions change those policies, so the upgrade stops without
them.

Adopt such a database only when it matches the initial migration in full:
the tables, the `users_isolation` and `tenants_isolation` policies, and
ENABLE and FORCE ROW LEVEL SECURITY on `users` and `tenants`. On such a
volume `lawbyai_owner` does not exist yet. Do these steps in order:

1. Stamp the initial revision with the bootstrap superuser connection. This
   creates the `alembic_version` table:
   `POSTGRES_OWNER_URL=<superuser URL> uv run alembic stamp 4439761c5e40`.
2. Upgrade to the revision before the RLS hardening, with the same
   connection. This creates the objects that the next step expects:
   `POSTGRES_OWNER_URL=<superuser URL> uv run alembic upgrade 77985ac8fa22`.
3. Do steps 1 and 2 of "Upgrade an old volume" below. They create the roles
   and give every object, `alembic_version` included, to `lawbyai_owner`.
4. Run `uv run alembic upgrade head` with the owner connection (step 3 below).

Do not stamp `head`, because the later revisions would then never run.

## Upgrade an old volume

The Postgres init script makes the database roles. It runs on a fresh volume
only. An old volume has one role, the bootstrap superuser (`POSTGRES_USER`),
and that role owns every object. The new migration stops on such a volume.
Use this procedure to move an old volume to the new role model.

The procedure makes three roles:

- `lawbyai_owner` runs the migrations and owns every object.
- `lawbyai_app` is the role that the app, the worker and the tests use. It owns
  nothing.
- `lawbyai_auth` cannot log in. It owns the login lookup function only.

You cannot use `REASSIGN OWNED BY` to change the owners. The old owner is the
bootstrap superuser, and Postgres does not reassign objects that a superuser
owns. The block changes the owner of each object one at a time.

1. Set `LAWBYAI_OWNER_PASSWORD` and `LAWBYAI_APP_PASSWORD` in the shell. Use
   the values from the Docker env file. Do not write a password in the SQL.
2. Run the block below with `psql -v ON_ERROR_STOP=1` as the bootstrap
   superuser, on the app database. This option stops `psql` at the first
   error. `psql` reads the two passwords from env with `\getenv`.
3. Run `uv run alembic upgrade head` with the owner URL. Set `POSTGRES_OWNER_URL` to
   a URL with the user `lawbyai_owner` and the owner password.

```sql
-- Read the passwords from env, so they are not in the SQL text.
\getenv owner_password LAWBYAI_OWNER_PASSWORD
\getenv app_password LAWBYAI_APP_PASSWORD
-- Keep the statement text (with the password) out of the server log on error.
SET log_min_error_statement = panic;
SET log_statement = 'none';

BEGIN;

-- The same roles, attributes and grants as the init script.
CREATE ROLE lawbyai_owner
  LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE
  PASSWORD :'owner_password';

CREATE ROLE lawbyai_app
  LOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT NOCREATEDB NOCREATEROLE
  PASSWORD :'app_password';

CREATE ROLE lawbyai_auth
  NOLOGIN NOSUPERUSER BYPASSRLS NOINHERIT NOCREATEDB NOCREATEROLE;

GRANT CREATE, USAGE ON SCHEMA public TO lawbyai_owner;
GRANT CREATE, USAGE ON SCHEMA public TO lawbyai_auth;
GRANT lawbyai_auth TO lawbyai_owner WITH INHERIT FALSE, SET TRUE;

-- Give each object to the owner role.
ALTER TABLE tenants OWNER TO lawbyai_owner;
ALTER TABLE users OWNER TO lawbyai_owner;
ALTER TABLE legal_document OWNER TO lawbyai_owner;
ALTER TABLE rejected_document OWNER TO lawbyai_owner;
ALTER TABLE alembic_version OWNER TO lawbyai_owner;
-- The sequence belongs to its table. Keep this line after the table line.
ALTER SEQUENCE rejected_document_id_seq OWNER TO lawbyai_owner;
ALTER FUNCTION users_bump_session_version() OWNER TO lawbyai_owner;

COMMIT;
```

The block runs in one transaction. If a statement fails, no change stays.
If the database has more objects that the superuser owns, change their owner
in the same way before you run the migration.
