# Path 1: separate actor contextvar

## Core idea
A new `core.security.actor` module copies the pattern of `tenant.py`. It holds the email of the authenticated admin in its own `ContextVar`. `reject(document_id)` reads the actor and raises an error before any write when the actor is missing or blank. One migration revokes UPDATE, DELETE and TRUNCATE on `rejected_document` from `lawbyai_app`.

## Components
- `src/core/security/actor.py` (new): `_ACTOR_VAR` (`"core.actor"`, default None) and these helpers:
  - `set_current_actor(actor: str | None) -> None`
  - `get_current_actor() -> str | None`
  - `reset_current_actor() -> None`
  - `actor_context(actor)`: a context manager that restores the previous value in `finally`.
  - `require_actor() -> str`: returns the stripped actor. It raises `MissingActorError` when the actor is None or blank.
- `src/core/security/__init__.py`: export the actor helpers, as it exports the tenant helpers.
- `src/ui/components/auth.py`: wrap each admin reject action in `actor_context(user.email)`. The email comes from `get_current_user()`. If no user is signed in, the actor is never set.
- `PostgreSQLStore.reject(self, document_id: str) -> None` (`src/plugins/relational_db/postgres.py:373`):
  - Remove the `admin` parameter.
  - Call `require_actor()` first.
  - Keep the DELETE and INSERT transaction as it is, with `admin=actor`.
- `migrations/versions/<new>_revoke_rejected_document_mutation.py`: `down_revision = "b7e2d41c9a30"`.

## Migration SQL
`b7e2d41c9a30` (lines 282-301) grants `SELECT, INSERT, UPDATE, DELETE` on `rejected_document` to the app role. It does not grant TRUNCATE.
- **upgrade:** `REVOKE UPDATE, DELETE, TRUNCATE ON public.rejected_document FROM lawbyai_app`. TRUNCATE has no effect, because the app role never had it. The statement still makes the denial explicit.
- **downgrade:** `GRANT UPDATE, DELETE ON public.rejected_document TO lawbyai_app`. This gives back the exact prior privileges, without TRUNCATE.

SELECT, INSERT and the sequence grants do not change. Alembic runs as `lawbyai_owner`, which owns the table.

## Data flow
1. The UI handler calls `get_current_user()`.
2. The handler opens `actor_context(email)` and calls `store.reject(doc_id)`.
3. `require_actor()` runs. A missing or blank actor raises `MissingActorError`, and no transaction opens.
4. The transaction runs DELETE RETURNING and then the INSERT of the audit row.
5. After the commit, the delete hook runs.
6. `actor_context` restores the previous actor.

## Tests
- **Unit:**
  - set, get and reset of the actor.
  - Nested `actor_context` restores the previous value.
  - The actor does not leak after an exception.
  - `require_actor` raises on None, `""` and `"   "`.
- **Store integration:**
  - With no actor, `reject` raises, the document is still there, and no audit row is written.
  - The actor in the audit row is the actor from the context.
  - `reject` has no `admin` parameter.
- **Privilege integration (as `lawbyai_app`):**
  - UPDATE, DELETE and TRUNCATE each fail with `42501`.
  - INSERT and SELECT succeed.
  - `has_table_privilege` returns false for UPDATE, DELETE and TRUNCATE.
- **Migration:**
  - upgrade, downgrade and upgrade again, as the owner.
  - After the downgrade, UPDATE and DELETE are granted again, and TRUNCATE is not.

## Failure modes
These cases are handled:
- A missing or blank actor raises an error before any write.
- `finally` clears a stale actor.
- A later `GRANT ALL` is caught by the `has_table_privilege` test.
- The downgrade is exact.

This case is not handled:
- In-process code can call `set_current_actor` with a false email. This is a trust boundary, not a technical block.

## Effort and risks
Effort: S.

Risks:
- The context variable must be set in the same call path as `reject`. Streamlit reruns and OS threads do not carry it.
- The signature of `reject` changes, so the tests that pass `admin` must change too.
