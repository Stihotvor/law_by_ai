# Decision: admin-user-management

## Context
No admin UI creates or deactivates users. Only the seed script creates users. The DB trigger `trg_users_session_version` already bumps `session_version` when `is_active` changes. The principal carries email and role only, with no user id and no tenant. See requirements.md.

## Options
- Path 1: store-centric. Rules inside `PostgreSQLStore`. Smallest diff. Testable only through the store.
- Path 2: hexagonal service layer. `core/users` service and a `UserRepository` port. The store is the adapter.
- Path 3: database-centric. SQL functions and triggers enforce the rules. The mutation gate does not measure plpgsql.
- Path 4: async Celery workflow. Effort L. The hash crosses Redis. The 1 second target is at risk.

## Decision
Path 2, chosen by the owner at the design gate.
- `src/core/users/` holds `service.py`, `ports.py` and `errors.py`. Every service call starts with `require_admin_principal()`.
- `PostgreSQLStore` gets `insert_user`, `list_users` and `deactivate_user` as the port adapter. The tenant comes from `get_current_tenant()`, never from an argument or the form.
- Deactivate runs in one transaction. It takes `SELECT ... FOR UPDATE` on the active admin rows of the tenant in id order, then recounts. It refuses self-deactivation and the last active admin. An inactive target returns with no `UPDATE`. A foreign id behaves as a missing row. The existing trigger bumps `session_version`.
- The page calls `require_admin()` first, then maps form fields to service calls and service errors to fixed messages.
- `require_admin`, `require_admin_principal` and `check_privilege_escalation` stay unchanged.

## Consequences
- No migration and no new dependency.
- Unit tests use a fake port. Integration tests use real Postgres, including a two-session test for the last-admin lock.
- A conformance test keeps the port and the store in step.
- Self-deactivation is matched by email, because the principal has no id. The email is unique and normalised, so the match is safe.
- `create_user` stays for the seed script. The service does not reuse it, because it skips validation and duplicate handling.
- Follow-up, needs owner approval: add the `trg_users_last_admin` trigger as a DB backstop. A DB audit table is also a follow-up.
- Open: the page file name and the minimum password length need a value at the ticket stage.
