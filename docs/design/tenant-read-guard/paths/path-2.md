# Path 2: ORM load, then a Python check for single rows

Lens: keep `session.get` for single-row calls and check ownership in Python, as `save_document` does with `_require_writable`. Lists filter in SQL.

## Changes
- `_owns(row, tenant) -> bool`: `row is not None and row.tenant_id == tenant`. `_require_writable` calls it, so the Python rule exists once.
- `get_document`: `session.get`, then `_owns`. A foreign row returns `None`.
- `delete_document`: `session.get`, then `_owns`, then `session.delete(row)` and commit. A foreign row is a no-op.
- `search_documents` and `get_recent_changes`: add `LegalDocument.tenant_id.is_not_distinct_from(T)` to the `WHERE` (a list cannot be filtered in Python without breaking `limit`).

## Fit
- T2, E1: met.
- T3: partly met. The rule exists twice: once in Python (`_owns`) and once in SQL (lists and `_owned_row_for_update`). A test must keep the two in step.
- F1-F3: met. The delete has a gap between load and delete, but `tenant_id` cannot change through the store, so the gap does not leak.

Effort: S. About 20 changed lines and one small helper.

## Risks
1. Two forms of one rule (Python and SQL) can drift apart.
2. A foreign row is loaded into the session before the check. It is not returned, but it is in process memory.
3. A delete of a row that a concurrent call already removed gives a SQLAlchemy warning on flush, not an error.
