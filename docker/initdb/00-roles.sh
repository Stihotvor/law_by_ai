#!/bin/sh
# Create the three database roles of rls-201 (see docs/design/rls-201/decision.md).
# The postgres image runs this file once, on an empty volume, as the bootstrap
# superuser (POSTGRES_USER). Old volumes need the manual SQL from the docs.
# The entrypoint sources a non-executable .sh file, so this file sets no shell
# options; the entrypoint already runs with `set -e`.
#
# lawbyai_owner  runs migrations and owns every object. No superuser, no BYPASSRLS.
# lawbyai_app    the app, worker and tests connect as this role. It owns nothing.
# lawbyai_auth   NOLOGIN, BYPASSRLS. Only the owner of auth_lookup_user.
#
# Passwords come from env; psql reads them with \getenv. None is written here.
# The table grants (column SELECT on users and the rest) live in the migration.

: "${LAWBYAI_OWNER_PASSWORD:?set LAWBYAI_OWNER_PASSWORD in docker/.env}"
: "${LAWBYAI_APP_PASSWORD:?set LAWBYAI_APP_PASSWORD in docker/.env}"

psql -v ON_ERROR_STOP=1 \
  --no-psqlrc \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" <<'SQL'
-- Read the passwords from env inside psql, so they never appear in argv.
\getenv owner_password LAWBYAI_OWNER_PASSWORD
\getenv app_password LAWBYAI_APP_PASSWORD
-- Keep the statement text (with the password) out of the server log on error.
SET log_min_error_statement = panic;
SET log_statement = 'none';

BEGIN;

CREATE ROLE lawbyai_owner
  LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE
  PASSWORD :'owner_password';

CREATE ROLE lawbyai_app
  LOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT NOCREATEDB NOCREATEROLE
  PASSWORD :'app_password';

CREATE ROLE lawbyai_auth
  NOLOGIN NOSUPERUSER BYPASSRLS NOINHERIT NOCREATEDB NOCREATEROLE;

-- PG15+ no longer grants CREATE on public to PUBLIC.
GRANT CREATE, USAGE ON SCHEMA public TO lawbyai_owner;
GRANT USAGE ON SCHEMA public TO lawbyai_auth;

-- The owner may SET ROLE lawbyai_auth to make it the function owner,
-- but does not inherit its BYPASSRLS. lawbyai_app gets no membership.
GRANT lawbyai_auth TO lawbyai_owner WITH INHERIT FALSE, SET TRUE;

COMMIT;
SQL
