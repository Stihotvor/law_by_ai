# Contract: tenant read guard (path 1, accepted)

Caller tenant `T` = `_resolve_tenant(tenant_id)`, the write-guard helper, unchanged. `T` can be `None`. `T` is never `""`.
Readable: `T` set gives `tenant_id = T OR tenant_id IS NULL`. `T` is `None` gives `tenant_id IS NULL`.
Owned (write and delete): `tenant_id IS NOT DISTINCT FROM T`.
Signatures and return types do not change. The protocol `src/core/plugins/protocols/relational_db.py` does not change.

## Callers (checked at `bc02a46`)
- `src/`: no callers. Only definitions (protocol, `postgres.py`). `src/core/security/rbac.py` has an unrelated `delete_document(document_id, role)`.
- `tests/`: `tests/integration/plugins/test_postgres.py`, `test_postgres_status_guard.py`, `test_postgres_tenant_guard.py`, `tests/integration/test_reject_document.py`, `tests/integration/tasks/test_fetch_close_store.py`, `tests/factories/plugins.py`. A test that reads a tenant row with no tenant, or deletes a row of another tenant or a shared row as a tenant, breaks. Task 1 checks each one.

## `get_document(document_id: str, tenant_id: str | None = None) -> dict[str, Any] | None`
Query: `SELECT ... WHERE id = :id AND <readable>`.
Inputs: `document_id` (str), `tenant_id` (optional, `""` counts as not given).
Outputs: the row as `doc_to_dict`, or `None` when the row is missing or not readable.
Errors: none new. Database errors pass through (unchanged).

## `search_documents(query: str, *, limit: int = 10, tenant_id: str | None = None) -> list[dict[str, Any]]`
Query: the existing `ILIKE` on title or content, AND `<readable>`, `ORDER BY last_updated DESC LIMIT :limit`.
Outputs: up to `limit` readable rows (own and shared), newest first. Foreign rows are omitted before the limit.
Errors: none new.

## `get_recent_changes(*, since: str | None = None, tenant_id: str | None = None) -> list[dict[str, Any]]`
Query: `<readable>`, AND `last_updated > since` when `since` is set, newest first. No `LIMIT` (unchanged, follow-up).
Outputs: all readable rows that match.
Errors: none new. A bad `since` string raises as today (`_parse_dt`).

## `delete_document(document_id: str, tenant_id: str | None = None) -> None`
Statement: `DELETE FROM legal_document WHERE id = :id AND <owned>`, then commit. One atomic statement.
Outputs: an owned row is deleted. A missing, foreign or (for a tenant caller) shared id deletes nothing. All return `None`.
Errors: none new. It does not raise `StoreDocumentNotFoundError`. It does not call `on_document_deleted` (unchanged, only `reject` calls it).

## Private helpers (`postgres.py`)
- `_readable_by(tenant: str | None) -> ColumnElement[bool]`: read predicate. `or_(LegalDocument.tenant_id == tenant, LegalDocument.tenant_id.is_(None))` when `tenant` is set, else `LegalDocument.tenant_id.is_(None)`. No error.
- `_owned_by(tenant: str | None) -> ColumnElement[bool]`: write predicate. `LegalDocument.tenant_id.is_not_distinct_from(tenant)`. `_owned_row_for_update` and `delete_document` use it. No error.
- `_require_writable` keeps its Python check for `save_document` (unchanged).

## Guard limit
A caller with no tenant can delete every shared row. The store does not check the role. Caller RBAC (`admin`, ADR-0013) is the only guard on this path until RLS exists.
