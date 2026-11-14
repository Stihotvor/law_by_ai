# rls-201 requirements

## Business Goals
- A bug in app code cannot read or write the `users` or `tenants` rows of another tenant.
- Login still works for every tenant, before any tenant is known.
- Why now: the login UI is merged, and the dba found that the RLS on `users` protects nothing.
- Out of scope: RLS on `legal_document` (a later issue). No change to the login UI.

## Technical Constraints
- PostgreSQL, SQLAlchemy, Alembic, Docker Compose. Runs on 4-6 GB RAM.
- Three roles: `lawbyai_owner` (runs migrations, owns tables), `lawbyai_app` (LOGIN, NOSUPERUSER, NOBYPASSRLS, owns nothing), `lawbyai_auth` (NOLOGIN, BYPASSRLS, column SELECT on `users` only).
- A Postgres init script in `docker-entrypoint-initdb.d` creates the roles. Passwords come from env.
- `public.auth_lookup_user(p_email text)`: LANGUAGE sql, STABLE, SECURITY DEFINER, `SET search_path = pg_catalog, pg_temp`, owner `lawbyai_auth`. EXECUTE only for `lawbyai_app`.
- `PostgreSQLStore.get_login_user` keeps its signature and calls the function.
- The migration keeps `lock_timeout`. The downgrade restores the old policies and drops the function. It keeps `ck_users_email_normalised`, which belongs to revision `77985ac8fa22`.

## Edge Cases
- Email `' A@x.PL '` matches the stored `a@x.pl` (lower and trim).
- Email `'%'`, `''` or an unknown email returns zero rows. No pattern match.
- A user with `is_active = false` is returned. The UI keeps its own reject.
- Mixed-case or duplicate emails: revision `77985ac8fa22` already adds `ck_users_email_normalised` with a pre-check. This issue keeps that CHECK.
- No tenant set during bootstrap or migrations: both still see all rows they need (see decision.md).

## Failure Modes
- Old volume without the new roles: the migration stops and names the missing roles. Docs give the SQL to create them.
- No tenant set: `SELECT count(*) FROM users` returns 0 (fail closed).
- Tenant A set: an INSERT of a tenant B row fails the WITH CHECK.
- The app never connects as a superuser or table owner.

## Success Metrics
- 0 rows visible in `users` and `tenants` with no tenant set, as `lawbyai_app`.
- `auth_lookup_user(' A@x.PL ')` returns exactly 1 row across 2 tenants with no tenant set.
- `rolsuper = false` and `rolbypassrls = false` for `current_user` in 100% of app and test connections.
- `pg_proc.prosecdef = true`, `search_path` set in `proconfig`, and 0 EXECUTE grants to PUBLIC.
- All Docker integration tests pass as `lawbyai_app`. diff-cover is 90% or more.
