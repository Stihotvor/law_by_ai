# Path 3: policy-only

Path 3 has one NOBYPASSRLS app role, and RLS policies alone allow the login read. It has no function and no `lawbyai_auth`.

## Components
- Roles: `lawbyai_owner` and `lawbyai_app`.
- Policies on `users` and `tenants` (fail closed): `tenant_id = nullif(current_setting('app.current_tenant', true), '')`.
- Policy `users_login` is FOR SELECT only. Its condition is that `email` equals `lower(btrim(current_setting('app.login_email', true)))` and that the setting is not empty.
- `CHECK (email = lower(btrim(email)))` plus the unique email gives at most one row.

## Migration
Check the roles and the emails. Add the CHECK. Replace the policies, and apply the grants. The downgrade restores the old policies.

## Code change
`get_login_user` sets `app.login_email` (transaction-local) and then runs the same select.

## Failure modes
All listed failure modes are handled. It deviates from the requirements: it has no function and no `lawbyai_auth`.

## Assessment
- Complexity: low.
- Effort: S to M.
- Main risk: any code on the app connection can set `app.login_email` and read one known user's full row, with `password_hash`, in any tenant. A policy cannot hide columns.
