# Requirements: last-admin backstop and admin action audit

## Business Goals
- A tenant always keeps at least one active admin. The rule holds for every writer, not only for `PostgreSQLStore.deactivate_user`.
- Every admin user action (create user, deactivate user) leaves an audit row that the app role cannot change or delete.
- The actor in the audit row is the active admin row of the request principal. A caller cannot write another actor.

## Technical Constraints
- PostgreSQL, Alembic, three roles (`lawbyai_owner`, `lawbyai_app`, `lawbyai_auth`). Alembic runs as `lawbyai_owner`.
- `users` has FORCE row level security with a tenant-only policy. A session sees and changes only rows of `app.current_tenant`.
- A new revision follows `81dde4a27be7`. It does not edit frozen revisions.
- `deactivate_user` already locks the active admins in id order and raises `LastAdminError` first. The trigger is the backstop.

## Edge Cases
- A direct UPDATE that sets `is_active = false` or `role <> 'admin'` on the last active admin: refused.
- A DELETE of the last active admin: refused.
- A `tenant_id` change of the last active admin (moves the admin out of the tenant): refused.
- One statement that changes all admins of a tenant: the last row is refused, so the statement fails as a whole.
- A change that leaves another active admin, or a change of a user or an inactive admin: allowed.
- Two sessions that remove two different admins at once: one waits, then is refused or aborted. The tenant never reaches zero.
- Owner maintenance (test cleanup, a tenant purge): the owner may skip the check with the transaction setting `app.skip_last_admin_check = 'on'`. The trigger ignores the setting for every other role.

## Failure Modes
- Two raw SQL sessions can deadlock (SQLSTATE 40P01). PostgreSQL aborts one. The invariant holds. The store path does not deadlock because it locks in id order.
- A superuser bypasses RLS and the check sees all rows. A `lawbyai_owner` session with no tenant sees no rows and is refused (fail closed).
- A downgrade that drops the audit table would lose audit data. It stops when the table holds rows.
