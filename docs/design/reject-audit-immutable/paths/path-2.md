# Path 2: single request principal

## Core idea
One frozen `RequestPrincipal(tenant_id, email, role)` holds the identity of the request. `require_auth()` sets it once in each request. `reject()` reads the principal. It requires the role `admin` and an email that is not blank. A new migration revokes UPDATE, DELETE and TRUNCATE on `rejected_document` from `lawbyai_app`.

## Components
- `src/core/security/principal.py` (new):
  - `@dataclass(frozen=True) RequestPrincipal(tenant_id: str, email: str, role: str)`.
  - Functions: `set_principal(p)`, `get_principal() -> RequestPrincipal | None` and `reset_principal()`.
  - `principal_context(p)`: restores the previous principal on exit.
  - `PrincipalRequiredError(PermissionError)`.
- `src/core/security/__init__.py`: exports the new names. `tenant.py` does not change.
- `src/ui/components/auth.py:251`: after `set_current_tenant`, call `set_principal(RequestPrincipal(...))`. The values come from the user dict that `require_auth()` reads from the DB.
- `auth.py`, `_sign_out` and `logout_button`: call `reset_principal()` next to `reset_current_tenant()`.
- `postgres.py:373`:
  - The signature becomes `reject(self, document_id: str) -> None`.
  - A guard runs before any session opens.
  - The guard raises `PrincipalRequiredError` if the principal is None, if `role != "admin"`, or if the email is blank.
- A new migration with `down_revision = "b7e2d41c9a30"`.

## Migration SQL
- **upgrade:** `REVOKE UPDATE, DELETE, TRUNCATE ON public.rejected_document FROM lawbyai_app`.
- **downgrade:** `GRANT UPDATE, DELETE ON public.rejected_document TO lawbyai_app`.

The downgrade gives back the exact prior privileges. `b7e2d41c9a30:285` grants only `SELECT, INSERT, UPDATE, DELETE`, so the downgrade does not grant TRUNCATE.

## Data flow
1. `require_auth()` sets the tenant and the principal on each rerun.
2. The admin rejects a document.
3. `store.reject(id)` validates the principal before it touches the DB.
4. One transaction runs DELETE RETURNING and then inserts the audit row with `admin=principal.email`.
5. On sign-out, the principal is reset.

## Tests
- **As `lawbyai_app`:**
  - UPDATE, DELETE and TRUNCATE each fail with `42501`.
  - INSERT and SELECT succeed.
  - `has_table_privilege` returns false for UPDATE, DELETE and TRUNCATE.
- **Migration, as the owner:**
  - upgrade, downgrade and upgrade again.
  - After the downgrade, UPDATE and DELETE are granted again, and TRUNCATE is not.
- **`reject()`:**
  - Each of these cases raises, writes 0 audit rows and keeps the document: no principal, a blank email, an email of spaces, and a role that is not admin.
  - The actor in the audit row is the principal's email.
  - `reject(id, admin="x")` raises `TypeError`.
- **Auth:**
  - `require_auth()` sets the principal.
  - Sign-out clears the principal.

## Failure modes
These cases are handled:
- A missing or blank actor raises an error before any write.
- A role that is not admin raises an error before any write.
- A stale principal is cleared by the reset and by the restore in `principal_context`.
- A later `GRANT ALL` is caught by the `has_table_privilege` test.

This case is not handled:
- In-process code can call `set_principal` with false values. This is a trust boundary.

## Effort and risks
Effort: M. The change touches the auth layer, the store, a new security module, a migration and the Docker-suite tests.

Risks:
- Streamlit threading: the principal must be set in the same script run as the `reject` call.
- The role string and the keys of the user dict are assumptions. Check them against `_public()` first.
- The tenant and the principal hold the same tenant id, so the two values can drift apart.
