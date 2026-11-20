# Path 1: store-centric monolith
Rules live in `PostgreSQLStore`. `create_user` is hardened and `deactivate_user` is new. Both call `require_admin_principal()` first. The tenant comes from `get_current_tenant()`, never from an argument. The page is a thin form.
- Deactivate: one transaction, `SELECT ... FOR UPDATE` on the tenant rows in id order, then the checks (missing or foreign, already inactive, self, last admin), then `UPDATE`. The existing trigger bumps `session_version`.
- Files: `postgres.py`, one page, error classes. About 3 files plus tests.
- Effort: S to M.
- Risks: the principal has only email and role, so self-detection compares emails. Dropping `tenant_id` from `create_user` breaks the seed script and tests. Rules are testable only through the store.
