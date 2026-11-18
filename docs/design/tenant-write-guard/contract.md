# Contract: tenant write guard (path 1, accepted)

Caller tenant `T` = `_resolve_tenant(tenant_id)`. `T` can be `None`. `T` is never `""`.
A row is writable when `row.tenant_id == T` (`None == None` is true).
`NotFound` = `StoreDocumentNotFoundError(KeyError)`, `str(exc) == "Document not found: <id>"`.
Row locks hold until commit or rollback.

## `PostgreSQLStore.save_document(document: dict[str, Any], tenant_id: str | None = None) -> str`
Load: `session.get(LegalDocument, id, with_for_update=True)`, then `_require_writable`.

Inputs:
- `document`: needs `title`, `content`, `source`, `source_url` for an insert. `id` optional. `status` and `tenant_id` keys are ignored.
- `tenant_id`: optional. Overrides the context. `""` counts as not given.

Outputs:
- No `id`, or `id` with no row: inserts a row with `tenant_id=T`, `status=needs_review`. Returns the id. Sets `document["id"]`.
- `id` of a writable row: copies allowlisted fields (`apply_update`). Keeps `status`, `tenant_id`, `id`. Returns the id.
- Logs one warning with the operation name and the dropped key names only (insert: `status`, `tenant_id`; upsert: `status`, `tenant_id`, unknown keys). No document id, no values.

Errors:
- `NotFound`: `id` of a row that is not writable. No write, no commit. `document` is not changed.
- `NotFound`: `StaleDataError` on flush. The session rolls back.
- `KeyError` (bare): a required insert field is missing (unchanged).
- `sqlalchemy.exc.IntegrityError`: concurrent insert of the same new id (unchanged, kept by a test).

## `PostgreSQLStore.update_document(document_id: str, document: dict[str, Any], tenant_id: str | None = None) -> None`
Load: `_owned_row_for_update(session, document_id, T)`. It runs `SELECT ... WHERE id = :id AND tenant_id IS NOT DISTINCT FROM :T FOR UPDATE`. It locks only an eligible row, so a foreign update never waits on the lock of the owner.

Inputs: `document_id` (str), `document` (partial fields), `tenant_id` (optional, `""` counts as not given).
Outputs: allowlisted fields are copied and committed. `status`, `tenant_id`, unknown keys are dropped. One warning logs the operation name and the key names only.
Errors:
- `NotFound`: no row, or the row is not writable. Same type and text for both. No write, no commit.
- `NotFound`: `StaleDataError` on flush. The session rolls back.

## `StoreDocumentNotFoundError`
- Base: `KeyError` (was `LookupError`). Still a `LookupError`.
- `__str__` returns the message without quotes.
- `reject` keeps its current behaviour and text.

## Private helpers (`postgres.py`)
- `_resolve_tenant(tenant_id: str | None) -> str | None`: `arg = tenant_id or None`. `t = arg if arg is not None else get_current_tenant()`. Returns `t or None`. No payload input. No error.
- `_owned_row_for_update(session: Session, document_id: str, tenant: str | None) -> LegalDocument`: returns the locked row, or raises `NotFound` when no eligible row exists.
- `_require_writable(row: LegalDocument | None, document_id: str, tenant: str | None) -> LegalDocument`: used by `save_document`. Returns the row, or raises `NotFound`.

## `mappers.apply_update(row, document) -> list[str]`
No change. It never writes `tenant_id`, `status` or `id`.

## Guard limit
A caller with no tenant can write every shared row. The store does not check the role. Caller RBAC (`admin`, ADR-0013) is the only guard on this path until RLS exists.
