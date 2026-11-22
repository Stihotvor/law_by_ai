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
- `deactivate_user(user_id)`: read the target under RLS. A missing or foreign id raises `UserNotFoundError`. Self is detected by comparing the target id with the actor row id, and it raises `SelfDeactivationError`. If the target is an admin, lock the tenant's active admin rows with `FOR UPDATE ORDER BY id` first, with no `LIMIT` and no `SKIP LOCKED`, and nothing else locked before. If the actor is not in the locked set, raise `PrincipalRequiredError`. If the locked set holds the target and has one row or fewer, raise `LastAdminError` (defence in depth: with a verified actor distinct from the target, the set always has two rows or more). An already inactive admin target is not in the locked set, so the call returns `False`. If the target has role `user`, lock the actor row `FOR SHARE` (role `admin`, active, same tenant), then lock the target `FOR UPDATE`. No row for the actor raises `PrincipalRequiredError`. Then `UPDATE users SET is_active = false WHERE id = :id AND is_active RETURNING id`. Zero rows means an idempotent no-op. Self is checked before last admin. The existing trigger bumps `session_version`.
- The page lives in `src/ui/pages/users.py`. `app.py` registers it in the same `is_admin` block as the fetch page. The page calls `require_admin()` first and maps errors to fixed messages.
- `PostgreSQLStore.create_user` keeps its signature. The seed script still uses it.
- `require_admin`, `require_admin_principal` and `check_privilege_escalation` stay unchanged.

## Port signatures
The `UserRepository` Protocol in `src/core/users/ports.py` has four methods. `PostgreSQLStore` implements all four with the same parameter names, kinds and defaults (T5 checks this).

Record type, in `ports.py`:
```python
class UserRecord(TypedDict):
    id: str
    tenant_id: str
    email: str
    role: str
    name: str
    is_active: bool
```
`UserRecord` never holds `password_hash` or `session_version`. `plugins/relational_db/mappers.py` adds `user_to_record(row: User) -> UserRecord`. The existing `user_to_dict` stays unchanged for `create_user` and `get_user_by_email`.

Methods:
```python
def find_active_admin(self, email: str) -> UserRecord | None: ...
def insert_user(
    self, *, email: str, password_hash: str, role: str, name: str, actor_id: str
) -> UserRecord: ...
def list_users(self) -> list[UserRecord]: ...
def deactivate_user(self, user_id: str, *, actor_id: str) -> bool: ...
```

Rules for each method in the store:
- Every method reads the tenant from `get_current_tenant()`. Every query adds a `tenant_id` predicate on top of RLS.
- `find_active_admin(email)`: the service passes the email from `normalise_email(principal.email)`. The store compares it exactly. It returns the row only if `role = 'admin'` and `is_active` are true. Otherwise it returns `None`. With no tenant set, it returns `None` and runs no SQL. It raises no domain error. The service maps `None` to `PrincipalRequiredError`.
- `insert_user(...)`: the service passes a normalised email and a bcrypt hash. The store sets a new `uuid4` id, the current tenant and `is_active = true`. The store locks the actor row `FOR SHARE` (role `admin`, active, same tenant) in the same transaction, before the insert. It returns the new record. Errors, in check order: `PrincipalRequiredError` with no tenant set, before any SQL. `PrincipalRequiredError` when the actor is not an active admin of the tenant (nothing is inserted). `UserCreateRefusedError` only for SQLSTATE 23505 on `uq_users_email`. Every other DB error is re-raised unmapped. The transaction rolls back on every error.
- `list_users()`: it keeps the existing name and has no parameters. Its return annotation changes from `list[dict[str, Any]]` to `list[UserRecord]`. It orders by email. With no tenant set, it returns `[]` and raises no error. DB errors propagate unmapped.
- `deactivate_user(user_id, *, actor_id)`: the service passes the `id` of the row that `find_active_admin` returned. The store does the self check inside the lock transaction, so the check and the update see the same state. It returns `True` when the update changed one row, and `False` for an idempotent no-op on an inactive target. Errors, in check order: `PrincipalRequiredError` with no tenant set, before any SQL. `UserNotFoundError` for a missing or foreign id. `SelfDeactivationError` when `user_id == actor_id`. `PrincipalRequiredError` when the actor is not an active admin of the tenant. `LastAdminError` when the locked admin set has one row or fewer. The transaction rolls back on every error.
- The store imports the domain errors from `core.users.errors` and `PrincipalRequiredError` from `core.security`. The `core.users` package still imports no `plugins.*`.
- The service audit event holds actor id, target id, action and the `changed` flag from `deactivate_user`.

- Actor check in the write transaction: `find_active_admin` stays a fast pre-check in the service (the principal holds an email, not a user id). The store re-checks the actor row under the same transaction and is the authority. The lock order is one rule: admin rows in id order first, then the non-admin target. Never take the actor `FOR SHARE` before the ordered admin lock, because two crossed deactivations would deadlock. The target role is read without a lock, which is safe while no API changes a role. A future role update must lock admin rows first.

## Consequences
- No migration and no new dependency. No new index: `ix_users_tenant_id` and `uq_users_email` serve the queries.
- Unit tests use a fake port. Integration tests use real Postgres, including a two-session test for the last-admin lock and leak tests with no tenant set at store level.
- A conformance test keeps the port and the store in step.
- A deactivated user's cookie fails both the `is_active` check and the `session_version` check on the next request.
- Accepted risk: the generic duplicate message still tells an admin that the email exists somewhere, because email is unique across tenants and login needs that.
- A future reactivate or demote must take the same admin lock set.
- Follow-ups, need owner approval: a `trg_users_last_admin` DB backstop, a DB audit table, and a fix of the stale `setting = ''` wording about `users` in the project CLAUDE.md. The wording is wrong for `users` since migration b7e2d41c9a30.
