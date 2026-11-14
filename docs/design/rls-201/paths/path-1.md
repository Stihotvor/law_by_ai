# Path 1: privileged database function

The app has one login role with no bypass. A SECURITY DEFINER function, owned by a NOLOGIN BYPASSRLS role, is the only cross-tenant read path.

## Components
- `docker/initdb/00-roles.sh` is mounted into `docker-entrypoint-initdb.d`. It creates three roles, with passwords from env.
- A new Alembic revision after `4439761c5e40`.
- `public.auth_lookup_user(p_email text)`: LANGUAGE sql, STABLE, SECURITY DEFINER, `SET search_path = pg_catalog, pg_temp`, owner `lawbyai_auth`.
- Compose and settings: the app, worker and test services use `lawbyai_app`. Migrations use `lawbyai_owner`.

## Roles and grants
- `lawbyai_owner` owns the tables and runs migrations.
- `lawbyai_app` is LOGIN, NOSUPERUSER and NOBYPASSRLS. It gets DML on the tables and EXECUTE on the function.
- `lawbyai_auth` is NOLOGIN and BYPASSRLS. It gets column SELECT on `users` only.
- The function has no EXECUTE for PUBLIC. Default privileges keep new tables private.

## Migration
1. Set `lock_timeout`. Check that the roles exist. Check the emails for mixed case and for duplicates.
2. Keep the existing email CHECK `ck_users_email_normalised` (revision `77985ac8fa22`).
3. Replace the policies with `tenant_id = nullif(current_setting('app.current_tenant', true), '')` (`id` on `tenants`), for USING and for WITH CHECK.
4. Create the function and the grants. The downgrade restores the old policies and drops the function. It keeps the email CHECK.

## Code change
`get_login_user` runs `SELECT * FROM auth_lookup_user(:e)`. The signature stays the same, and `without_tenant()` is no longer needed.

## Failure modes
All listed failure modes are handled. Open: the bootstrap must create the first tenant and admin with no tenant set.

## Assessment
- Complexity: moderate.
- Effort: M.
- Main risk: the function is the single point of trust. A wrong `search_path` or grant reopens cross-tenant reads. The pg_proc metrics cover this.
