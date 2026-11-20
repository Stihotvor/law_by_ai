# Decision: last-admin backstop and admin action audit

## Context
The last-admin rule lives in the store only. Direct SQL and future paths (reactivate, role change) can leave a tenant with no admin. The admin actions are only a structured log event.

## Decision
The solution-architect and the DBA reviewed the design. Both agree on the points below.

### Trigger
- One migration revision, `down_revision = "81dde4a27be7"`.
- Function `public.users_guard_last_admin()`, plpgsql, SECURITY INVOKER, owner `lawbyai_owner`, `SET search_path = pg_catalog, pg_temp`, every name schema-qualified, no EXECUTE for PUBLIC.
- Trigger `trg_users_last_admin`: `BEFORE UPDATE OF is_active, role, tenant_id OR DELETE ON users FOR EACH ROW`.
- The body acts only when `OLD` is an active admin and the change removes it (delete, demotion, deactivation, tenant move).
- It locks the other active admins of `OLD.tenant_id` with `FOR NO KEY UPDATE` in id order. If it finds none, it raises SQLSTATE `23514` with `CONSTRAINT = 'trg_users_last_admin'`.
- Why invoker: RLS shows the session every admin of the tenant it can change, so a DEFINER function adds nothing. Why row locks and not a tenant-row mutex: row locks stay correct under REPEATABLE READ, which fails with 40001.
- Owner bypass: `current_user = 'lawbyai_owner'` and `app.skip_last_admin_check = 'on'`. The app role cannot use it. Test helpers that run as the owner set it.

### Audit table
- `admin_action_audit(id bigint identity, tenant_id, actor_id, action, target_id, created_at timestamptz default now())`. No foreign keys, so rows outlive users. `CHECK` on `action`.
- RLS enabled and forced, tenant-only policy with `WITH CHECK`. `lawbyai_app` gets SELECT and INSERT only. The rows are kept forever.
- Writer: the store, in the same transaction as the action. A trigger cannot see the actor id without a spoofable session setting. The service already resolves the actor id.
- The store write is a separate commit after the schema commit. Another session edits the same files, so that commit is rebased last.

### Downgrade
Drop the trigger, the function, then the table. It stops with an error if the audit table holds rows.
