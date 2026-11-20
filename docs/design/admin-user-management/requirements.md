# Requirements: admin-user-management

An admin-only Streamlit page to create and deactivate users. Follow-up left out of scope by the login UI task.

## Business Goals
- A tenant admin adds and removes users from the UI. Today only the seed script creates users.
- Scope is create, list and deactivate. Reactivate, password reset and role change are out of scope.
- A new user joins the admin's own tenant. The tenant comes from the tenant context that login sets, never from the form.
- Test: an admin creates a user who then logs in. An admin deactivates that user and the user cannot log in again.

## Technical Constraints
- ADR-0013: streamlit-authenticator, bcrypt through `hash_password`, RBAC `admin` and `user`. ADR-0003: tenant isolation by `tenant_id` and RLS.
- Facts in the code: `users.email` is unique across tenants and the DB checks `email = lower(btrim(email))`. The trigger `trg_users_session_version` bumps `session_version` when `is_active` or `password_hash` changes. `PostgreSQLStore` has no `deactivate_user`. `create_user` does not validate the role and does not handle a duplicate email.
- The admin can create both roles. The server validates the role with `valid_role`. The form never sets the tenant.
- The admin types the initial password. The server enforces 12 or more characters and at most 72 UTF-8 bytes (the `init_stack` limits), hashes it, and never logs or shows it. Email is at most 256 characters, name is at most 256.
- The server refuses self-deactivation and deactivation of the last active admin of the tenant.
- No change weakens `require_admin`, `require_admin_principal` or `check_privilege_escalation`. The page calls `require_admin()` first, and the service re-checks the principal on the server side.
- Tenant guard rules apply: the tenant comes from `get_current_tenant()`, never an argument. An empty tenant raises an error before any SQL. A foreign row behaves as a missing row.
- Python 3.13, Streamlit, SQLAlchemy, PostgreSQL. No new dependency.

## Edge Cases
- A duplicate email, in the own tenant or another tenant, shows one generic message: "Cannot create this user." The page does not reveal that the email exists elsewhere.
- Email input is trimmed and lowercased before the write. A blank or malformed email is refused.
- A role outside `VALID_ROLES` is refused on the server.
- Deactivating an already inactive user is idempotent: no error and no extra `session_version` bump.
- Deactivating an id from another tenant or an unknown id behaves as a missing row.
- Two admins deactivate the last two admins at the same time: the last-admin check must hold under concurrency.
- A user with role `user` opens the page URL directly: the page stops with "Admin role required." and no data loads.
- A demoted or deactivated admin loses the page on the next request.

## Failure Modes
- Each action is one transaction. On a DB error the page shows a generic error and no stack trace.
- A DB error can mean the commit outcome is unknown: PostgreSQL may commit and the connection may fail before the client sees the reply. The page message says so: "Database error. Check the user list before you try again." The admin checks the user table before a retry. A retried create of an existing email gets the generic duplicate message, and a retried deactivate is an idempotent no-op, so a retry is safe.
- The log never holds a password or a hash.
- Audit is a structured log event (stdlib `logging`, `extra` fields; structlog is not a dependency yet) with actor id, target id and action. A DB audit table is a follow-up, not in scope.
- If the redis or login lookup is down, the existing login behaviour stays unchanged.
- The admin sees a clear error for invalid input. The admin never sees a stack trace.

## Success Metrics
- Integration test: the old cookie of a deactivated user fails on the next request because `session_version` differs.
- Leak tests: 0 cross-tenant rows read or written by the new store methods.
- Role `user`: 0 successful calls to create or deactivate, at page level and at service level.
- Tests cover create, deactivate, duplicate email and privilege escalation, as unit and integration tests.
- New code meets the repo coverage and mutation gates (CONTRIBUTING.md).
- Page action on local Postgres returns in under 1 second.
