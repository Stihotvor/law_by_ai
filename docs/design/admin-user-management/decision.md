# Decision: admin-user-management

## Context
No admin UI creates or deactivates users. Only the seed script creates users. The DB trigger `trg_users_session_version` bumps `session_version` when `is_active` changes. The principal has email and role only, with no user id and no tenant. The `users` RLS policy is tenant-only: with no tenant set, a list returns no rows and an insert fails the `WITH CHECK`. See requirements.md.

## Options
- Path 1: store-centric. Rules inside `PostgreSQLStore`. Smallest diff. Testable only through the store.
- Path 2: hexagonal service layer. `core/users` service and a `UserRepository` port. The store is the adapter.
- Path 3: database-centric. SQL functions and triggers enforce the rules. The mutation gate does not measure plpgsql.
- Path 4: async Celery workflow. Effort L. The hash crosses Redis. The 1 second target is at risk.

## Decision
Path 2, chosen by the owner at the design gate. The architect and DBA reviewed it and approved it with the changes below.
- `src/core/users/` holds `service.py`, `ports.py` and `errors.py`. It imports only `core.security` and its own port. It imports no `plugins.*` and no `streamlit`. The page wires `PostgreSQLStore` into the service.
- Errors: `UserCreateRefusedError`, `UserNotFoundError`, `SelfDeactivationError`, `LastAdminError`, plus `PrincipalRequiredError` from core.
- Every service call: raise `PrincipalRequiredError` if `get_current_tenant()` is empty. Then call `require_admin_principal()`. Then load the actor row by normalised principal email under the tenant. It must be an active admin, or the call raises `PrincipalRequiredError`. This binds the principal to the tenant and gives the actor id for the audit event.
- The tenant comes from `get_current_tenant()`, which login sets (`auth.py`). It is never an argument or a form field.
- `create_user(email, password, role, name)` returns `{id, tenant_id, email, role, name, is_active}`. Validation: password 12 or more characters and 72 or fewer UTF-8 bytes (move the `init_stack` constants to `core.security.passwords`), email with one `@` and at most 256 characters, name at most 256, role by `valid_role`. Every failure raises `UserCreateRefusedError`. `hash_password` always runs before the insert. There is no existence pre-check. The adapter maps only SQLSTATE 23505 on `uq_users_email` to `UserCreateRefusedError`. Any other DB error stays a generic DB error. Roll back on every error.
- `list_users()` reuses the existing store method and adds a `tenant_id` predicate on top of RLS. It orders by email. It returns records without the hash.
- `deactivate_user(user_id)`: read the target under RLS. A missing or foreign id raises `UserNotFoundError`. Self is detected by comparing the target id with the actor row id, and it raises `SelfDeactivationError`. If the target is an admin, lock the tenant's active admin rows with `FOR UPDATE ORDER BY id` first, with no `LIMIT` and no `SKIP LOCKED`, and nothing else locked before. If the locked set has one row or fewer, raise `LastAdminError`. If the target has role `user`, lock only the target. Then `UPDATE users SET is_active = false WHERE id = :id AND is_active RETURNING id`. Zero rows means an idempotent no-op. Self is checked before last admin. The existing trigger bumps `session_version`.
- The page lives in `src/ui/pages/users.py`. `app.py` registers it in the same `is_admin` block as the fetch page. The page calls `require_admin()` first and maps errors to fixed messages.
- `PostgreSQLStore.create_user` keeps its signature. The seed script still uses it.
- `require_admin`, `require_admin_principal` and `check_privilege_escalation` stay unchanged.

## Consequences
- No migration and no new dependency. No new index: `ix_users_tenant_id` and `uq_users_email` serve the queries.
- Unit tests use a fake port. Integration tests use real Postgres, including a two-session test for the last-admin lock and leak tests with no tenant set at store level.
- A conformance test keeps the port and the store in step.
- A deactivated user's cookie fails both the `is_active` check and the `session_version` check on the next request.
- Accepted risk: the generic duplicate message still tells an admin that the email exists somewhere, because email is unique across tenants and login needs that.
- A future reactivate or demote must take the same admin lock set.
- Follow-ups, need owner approval: a `trg_users_last_admin` DB backstop, a DB audit table, and a fix of the stale `setting = ''` wording about `users` in the project CLAUDE.md. The wording is wrong for `users` since migration b7e2d41c9a30.
