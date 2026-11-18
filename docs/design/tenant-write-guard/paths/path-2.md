# Path 2: set-based conditional SQL

Lens: the tenant predicate lives in one SQL statement per write. There is no read-then-write in Python.

## Changes
- `mappers.build_update_values(document) -> tuple[dict, list[str]]` replaces `apply_update`. It maps allowlisted keys to columns and returns (values, sorted dropped keys).
- `_resolve_tenant(tenant_id: str | None) -> str | None`: same rule as path 1.
- `_update_owned(session, doc_id, tenant, values) -> bool`: `UPDATE ... WHERE id = :id AND tenant_id IS NOT DISTINCT FROM :tenant RETURNING id`.
- `_upsert_owned(session, doc_id, tenant, insert_values, update_values) -> bool`: `INSERT ... ON CONFLICT (id) DO UPDATE SET ... WHERE legal_document.tenant_id IS NOT DISTINCT FROM :tenant RETURNING id`.
- `save_document` and `update_document`: zero rows returned means missing or foreign. Both raise `StoreDocumentNotFoundError("Document not found: <id>")`.
- `StoreDocumentNotFoundError(KeyError)`: base change only.

## Error flow
Zero rows means no commit. The row is unchanged.

## Fit
- T2, E1, E5: the resolved tenant is a bound parameter. `IS NOT DISTINCT FROM` gives `NULL == NULL`.
- F1-F3: met. Check and write are one atomic statement (no race window).
- F4: unchanged and accepted.
- F5: changed. Two inserts of the same new id give no `IntegrityError`. `ON CONFLICT DO UPDATE` makes the second call an update when both callers have the same tenant. When the tenants differ, the conflict `WHERE` fails and the second call raises `StoreDocumentNotFoundError`.

Effort: M. Two write paths rewritten, mapper changes shape, `apply_update` tests migrate.

## Risks
1. PostgreSQL-only SQL. Unit tests that do not use PostgreSQL move to the integration marker.
2. Core statements skip the ORM unit of work. ORM defaults, `onupdate` hooks and JSON type coercion need a check.
3. An empty values dict makes `UPDATE ... SET` invalid. It needs a fallback (`SET id = id` or an ownership `SELECT`).
4. Insert and update value sets can drift apart.
