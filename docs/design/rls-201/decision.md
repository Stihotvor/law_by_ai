# rls-201 decision

## Context
The app, the worker, the tests and Alembic all connect as one role (`POSTGRES_USER`). That role is the bootstrap superuser and the table owner, so it bypasses RLS. The policies on `users` and `tenants` also allow every row when `app.current_tenant = ''`. The login lookup must read one user across tenants before any tenant is known.

## Options
- Path 1, privileged database function: one NOBYPASSRLS app role. A SECURITY DEFINER `auth_lookup_user` is the only cross-tenant read. Effort M.
- Path 2, split connections: a second engine connects as a BYPASSRLS login role for the lookup. Effort M.
- Path 3, policy-only: an extra SELECT policy keyed on `app.login_email`. Effort S to M.
- Path 4, schema split: a global `auth.credentials` table, separate from `users`. Effort L.

| | Path 1 | Path 2 | Path 3 | Path 4 |
|---|---|---|---|---|
| Fit to constraints | all items | no function, LOGIN auth role | no function, no auth role | all items, plus a model split |
| Handles failure modes | yes | yes | yes | yes |
| Complexity | moderate | two engines, two secrets | low | high |
| Effort | M | M | S-M | L |
| Main risk | function grants or search_path | app holds a BYPASSRLS login | forged setting reads a hash | write paths drift |

## Decision
The user chose Path 1. Reasons:
- It meets every requirement and every metric, including the pg_proc checks.
- The cross-tenant login path returns at most one row with fixed columns, by exact email. RLS stops app queries that leave out the tenant. RLS does not stop SQL injection, because injected SQL can set `app.current_tenant` itself. Parameterized SQL is still the defence against injection.
- It adds no runtime component and does not move data.

## Consequences
These items include the fixes from the dba review and the solution-architect review.

### Roles (init script `docker/initdb/00-roles.sh`, fresh volumes only)
- `lawbyai_owner`: LOGIN, NOSUPERUSER, NOBYPASSRLS. It gets `CREATE, USAGE ON SCHEMA public` (PG15+ needs this). It runs migrations and owns every object.
- `lawbyai_app`: LOGIN, NOSUPERUSER, NOBYPASSRLS, NOINHERIT, NOCREATEDB, NOCREATEROLE. It owns nothing.
- `lawbyai_auth`: NOLOGIN, BYPASSRLS, NOINHERIT, NOCREATEDB, NOCREATEROLE. It gets CREATE and USAGE on `public` (ALTER FUNCTION ... OWNER needs CREATE for the new owner) and column SELECT on `users (id, tenant_id, email, role, name, is_active, password_hash, session_version)` only.
- `GRANT lawbyai_auth TO lawbyai_owner WITH INHERIT FALSE, SET TRUE`, so the owner can set the function owner. Recorded risk: the owner can `SET ROLE` to a BYPASSRLS role and create objects that this role owns. The app cannot. A test checks that `lawbyai_auth` owns only `auth_lookup_user`.
- Passwords come from env. Compose passes them to postgres.

### Connections and migrations
- Settings get a separate owner URL for migrations. `migrations/env.py` and the init service use it.
- `PostgreSQLStore.initialize()` no longer runs Alembic upgrade. It only checks that the DB is at head, and fails clearly if not. `lawbyai_app` gets SELECT on `alembic_version`.
- The app, the worker and the tests connect as `lawbyai_app`.
- The init service runs `alembic upgrade head` with the owner URL. It then runs the bootstrap store with the app URL, so `get_login_user` has EXECUTE.
- The test service runs `alembic upgrade head` with the owner URL before pytest, because `initialize()` no longer migrates.

### Migration (new revision, `down_revision = "77985ac8fa22"`, `SET LOCAL lock_timeout = '5s'`)
1. Check that the three roles exist, and that `lawbyai_owner` owns `tenants`, `users`, `legal_document`, `rejected_document` and `alembic_version`. If not, stop and name what is missing.
2. A migration that reads data runs `ALTER TABLE ... NO FORCE ROW LEVEL SECURITY` and then `FORCE` again in the same transaction (user decision). A test asserts that FORCE is on at head.
3. `users.tenant_id` is already NOT NULL (since `4439761c5e40`), so this revision does not change it. Every row read of this revision runs inside the NO FORCE window of step 2. `ALTER TABLE ... NO FORCE/FORCE` takes ACCESS EXCLUSIVE under the 5s `lock_timeout`. Step 1 also checks the owner of the function `users_bump_session_version`.
4. `ALTER POLICY` (names kept) to `tenant_id = nullif(current_setting('app.current_tenant', true), '')` (`id` on `tenants`), for USING and WITH CHECK. No tenant means zero rows.
5. Create `public.auth_lookup_user(p_email text) RETURNS TABLE (id, tenant_id, email, role, name, is_active, password_hash, session_version)`: LANGUAGE sql, STABLE, STRICT, SECURITY DEFINER, `SET search_path = pg_catalog, pg_temp`. The body reads `public.users WHERE email = lower(btrim(p_email))`. Run `ALTER FUNCTION ... OWNER TO lawbyai_auth`, `REVOKE EXECUTE ... FROM PUBLIC` and `GRANT EXECUTE ... TO lawbyai_app`.
6. Grants for `lawbyai_app`: DML on `tenants`, `users`, `legal_document` and `rejected_document`, USAGE and SELECT on the `rejected_document` id sequence, and SELECT on `alembic_version`. `ALTER DEFAULT PRIVILEGES FOR ROLE lawbyai_owner REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC`. Each later migration grants per table.
7. The downgrade drops the function, revokes the grants, restores the old policies with ALTER POLICY exactly as `4439761c5e40` defines them, and undoes the `ALTER DEFAULT PRIVILEGES` revoke. It keeps `ck_users_email_normalised`, which belongs to `77985ac8fa22`.

### Code
- `get_login_user` calls `auth_lookup_user` and keeps its signature and its dict keys. `without_tenant()` is no longer needed there.
- The bootstrap (`src/bootstrap/init_stack.py`) runs `ensure_tenant` and the admin step inside the tenant context of `INIT_TENANT_ID`. It finds the admin through `get_login_user`.
- `list_tenants` has only the bootstrap as a caller, and it now returns the current tenant only.
- `get_user_by_email` stays tenant-scoped. Its docstring says that it returns None with no tenant set.
- Update the module docstring and the `TENANT_SETTING` comment in `postgres.py`.

### Old volumes
The docs give the SQL to create the roles and to run per-object `ALTER ... OWNER TO lawbyai_owner` for the tables, the `rejected_document` sequence and the function `users_bump_session_version`. The docs SQL also mirrors the init script: `CREATE, USAGE ON SCHEMA public` for the owner and `GRANT lawbyai_auth TO lawbyai_owner WITH INHERIT FALSE, SET TRUE`. `REASSIGN OWNED` cannot be used, because the old role is the bootstrap superuser.

### Tests
- Fixtures create and truncate data as the owner inside a tenant context, and assert as `lawbyai_app`.
- The test service depends on the init script roles. CI starts from a fresh volume.
- Fix the tests that use users with no tenant: `test_users_login_store.py`, `test_login_flow.py` and `test_init_stack.py`.
- Extra metrics: `proowner = lawbyai_auth`, `has_function_privilege('public', ..., 'EXECUTE') = false`, the app cannot `SET ROLE lawbyai_auth`, and FORCE RLS is on at head.

### Accepted trade-offs
- We give up the smaller effort of Path 3 and the full data split of Path 4.
- Residual leak: `uq_users_email` is global, so `create_user` shows whether an email exists in another tenant.
