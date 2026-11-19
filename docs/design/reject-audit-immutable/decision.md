# Decision: reject audit is append-only

## Context
The app role `lawbyai_app` can UPDATE and DELETE rows in `rejected_document`, so the audit log of admin rejects is mutable. `PostgreSQLStore.reject` takes the actor as a free `admin` argument, so a caller can write any email. No production code calls `reject()` yet. Only tests call it. The owner chose these rules:
- Rows are kept forever.
- Only the migration owner keeps the rights to change or delete rows.
- The actor comes from the request context.

The owner delegated the G1 choice to the solution-architect and the DBA.

## Options
- Path 1: a separate actor context variable (`core.security.actor`), which the caller sets around each reject call. It has no role check. Effort S.
- Path 2: one request principal (tenant, email, role), which `require_auth()` sets on each rerun. The store checks the admin role. Effort M.

## Decision
Path 2, reduced. The solution-architect picked it, and the DBA preferred it. The DBA's fixes F1 to F4 are added.

### Principal
- New module `src/core/security/principal.py`:
  - `@dataclass(frozen=True) RequestPrincipal(email: str, role: str)`. It has no `tenant_id`, so it cannot drift from the tenant context.
  - Functions: `set_principal(p)`, `get_principal() -> RequestPrincipal | None` and `reset_principal()`.
  - A `principal_context(p)` context manager, which restores the previous value on exit.
  - `require_admin_principal() -> RequestPrincipal`. It raises `PrincipalRequiredError(PermissionError)` in each of these cases:
    - the principal is None,
    - the role is not `core.security.ADMIN` (`rbac.py:25`),
    - the email is blank after `strip()`.

    It returns the principal with the stripped email.
- `src/core/security/__init__.py` exports the new names.

### Auth layer
- `require_auth()` (`src/ui/components/auth.py:251`) calls `set_principal(RequestPrincipal(user["email"], user["role"]))` next to `set_current_tenant`.
- `_sign_out` (`auth.py:229`) and `logout_button` (`auth.py:286`) call `reset_principal()` next to `reset_current_tenant()`.

### Store
`PostgreSQLStore.reject(self, document_id: str) -> None`:
- The `admin` parameter is removed.
- `require_admin_principal()` runs first, before any session opens.
- The DELETE RETURNING and the audit INSERT stay in one transaction, with `admin=principal.email`.

### Migration
A new revision with `down_revision = "b7e2d41c9a30"`. Alembic runs it as `lawbyai_owner`.
- **upgrade:** `SET LOCAL lock_timeout = '5s'`, then `REVOKE UPDATE, DELETE, TRUNCATE ON public.rejected_document FROM lawbyai_app`.
- **downgrade:** `SET LOCAL lock_timeout = '5s'`, then `GRANT UPDATE, DELETE ON public.rejected_document TO lawbyai_app`. TRUNCATE is not granted, because `b7e2d41c9a30:285` never granted it.
- SELECT, INSERT and the sequence grants do not change.
- The docstring states the retention rule: rows are kept forever, and only the owner can fix or purge a row.

### Tests
- **DBA fix F1.** These cleanup fixtures run `DELETE FROM rejected_document` and must connect as the owner through `get_settings().postgres_owner_url`, as `tests/integration/plugins/test_postgres.py:32-33` does for TRUNCATE. Where one transaction deletes from `legal_document` and `rejected_document`, move the whole block to the owner engine:
  - `tests/integration/test_fetch_rejection.py:51`
  - `tests/integration/test_fetch_worker_pool.py:60-63`
  - `tests/integration/test_fetch_task_integration.py:68-71`
  - `tests/integration/test_reject_document.py:49`
- **Reject calls.** Change the 12 test calls `reject(id, admin)` to use `principal_context`. A new thread does not inherit context variables, so each `_worker` in the concurrency test (`tests/integration/test_reject_document.py:178-181`) enters `principal_context` itself.
- **DBA fix F2.** The migration sets `lock_timeout` (see Migration).
- **Privileges, as `lawbyai_app`.** Run each statement in its own transaction:
  - UPDATE, DELETE and TRUNCATE each fail with `42501`.
  - INSERT and SELECT succeed.
- **Schema guard** (reads the schema after `alembic upgrade head`, not a fixed revision).
  - `has_table_privilege` returns false for UPDATE, DELETE and TRUNCATE.
  - `has_any_column_privilege(..., 'UPDATE')` returns false (DBA fix F3).
  - PUBLIC has no rights on the table.
- **Migration, as the owner.**
  - upgrade, downgrade and upgrade again.
  - After the downgrade, UPDATE and DELETE are true and TRUNCATE is still false (DBA fix F4).
- **`reject()`.**
  - These cases each raise and leave 0 audit rows and the document in place: no principal, a blank email, an email of spaces, and a role that is not admin.
  - The actor in the audit row equals the principal's email.
- **Auth.**
  - `require_auth()` sets the principal.
  - Sign-out clears the principal.

## Consequences
- `reject` must run in the same Streamlit script run as `require_auth()`, after `require_admin`.
- These are known limits:
  - A Celery task or other non-UI caller has no principal, so it cannot reject.
  - In-process code can still call `set_principal`. This is a trust boundary inside the process.
- These items are out of scope and become follow-ups:
  - a reject UI page and its error display,
  - recording the retention rule in ADR-0016, which needs its own `adr/` PR,
  - an actor for callers outside the UI.
