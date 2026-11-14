# Path 4: schema split

Login data moves to a global `auth.credentials` table. It has strict grants and no tenant RLS. `users` keeps only tenant data under fail-closed RLS.

## Components
- `auth.credentials(user_id PK/FK, email UNIQUE CHECK(email = lower(btrim(email))), password_hash, role, tenant_id, is_active, session_version)`.
- `public.users(id, tenant_id, name)` and `public.tenants` keep RLS. Policy: `tenant_id = NULLIF(current_setting('app.current_tenant', true), '')`.
- `auth_lookup_user(p_email)` (SECURITY DEFINER) is the only read path into `auth`.

## Roles and grants
- `lawbyai_owner` owns the schema and the tables, and runs migrations.
- `lawbyai_app` is LOGIN, NOSUPERUSER and NOBYPASSRLS. It has no USAGE on `auth`, and EXECUTE on the function only.
- `lawbyai_auth` is NOLOGIN. It has SELECT on `auth.credentials`, and it does not need BYPASSRLS.
- The function has no EXECUTE for PUBLIC. `ALTER DEFAULT PRIVILEGES` keeps new tables private. An init script creates the roles.

## Migration
1. Check that the roles exist. Check the emails for mixed case and for duplicates.
2. Create the schema and the table, and backfill them from `users`.
3. Drop the credential columns from `users`. Replace the policies.
4. Create the function and the grants. The downgrade copies the columns back.

## Code change
- `get_login_user` calls the function.
- `create_user`, `bump_session_version` and the bootstrap need more definer functions for writes.

## Failure modes
All listed failure modes are handled. The definer write functions bypass tenant checks by design.

## Assessment
- Complexity: high. This is a data move plus a model split.
- Effort: L.
- Main risk: the write paths of `users` and `credentials` drift apart, and old code that expects `users.email` breaks.
