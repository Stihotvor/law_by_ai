# Decision: tenant write guard

Status: accepted (owner, 2026-11-18). Path 1, all five defaults, and the dba changes.

## Context
`save_document` lets a payload `tenant_id` pick the tenant on insert. `save_document` (upsert) and `update_document` load rows by id with no tenant filter. `legal_document` has no RLS. Size S (one module, no schema change), so two paths were compared.

## Options
- Path 1, ORM load-then-check: `session.get`, then a Python ownership helper, then `apply_update`.
- Path 2, set-based conditional SQL: `UPDATE ... WHERE tenant IS NOT DISTINCT FROM` and `INSERT ... ON CONFLICT DO UPDATE ... WHERE`.

| Row | Path 1 | Path 2 |
|---|---|---|
| Fit to constraints (T1-T6) | Full. No new SQL dialect use. | Full. PostgreSQL-only SQL. |
| Failure modes F1-F3 | Met | Met |
| Race between check and write | Closed by `with_for_update` (dba change) | Closed (one statement) |
| Complexity | 2 helpers, `apply_update` unchanged | New values builder, 2 Core statements, empty-SET fallback |
| Effort | S | M |
| Main risk | Guard lives in Python only | ORM hooks and type coercion skipped |

## Decision
Path 1, with these rules.
- Tenant: `_resolve_tenant` changes `""` to `None`, then uses the `tenant_id` argument if not `None`, else `get_current_tenant()` (also `""` to `None`). Payload `tenant_id` is dropped and logged by name.
- Load: `session.get(LegalDocument, id, with_for_update=True)` in `save_document` and `update_document`.
- Ownership: `row.tenant_id == tenant`, `NULL == NULL`. Tenant rows are writable only by that tenant. Shared rows are writable only with no tenant.
- Error: `StoreDocumentNotFoundError`, base changed to `KeyError`, plain `__str__`. Same text `Document not found: <id>` for missing and foreign rows. `StaleDataError` on flush maps to the same error.
- Upsert of a foreign id raises. It never inserts a new id and never overwrites. The payload dict stays unchanged.
- Argument and context differ: the argument wins.

## Consequences
- The race between check and write is closed. The row lock holds until commit.
- `update_document` raises `StoreDocumentNotFoundError` instead of bare `KeyError`. `except KeyError` still works.
- `reject` callers that catch `StoreDocumentNotFoundError` or `LookupError` keep working.
- A caller with no tenant can write every shared row. Caller RBAC (`admin` role) is the only guard until RLS exists.
- Two inserts of the same new id still race. The second raises `IntegrityError`, and a test keeps this.
- Residual oracle: on `save_document`, an unknown caller-chosen id inserts, and a foreign id raises (accepted risk).
- Follow-ups (not in this task): server-generated ids only (no caller-chosen ids). Tenant filter on `get_document`, `search_documents`, `get_recent_changes`, `delete_document`. RLS on `legal_document`.
