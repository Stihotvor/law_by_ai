# Path 1: ORM load-then-check (accepted)

Lens: load the row with `session.get`, then compare tenants in Python through one helper. Writes stay ORM attribute writes through `apply_update`.

## Changes (all in `postgres.py`, `mappers.py` unchanged)
- `StoreDocumentNotFoundError(KeyError)`: base changes from `LookupError` to `KeyError`. Add `__str__` that returns the plain message, because `str(KeyError("x"))` adds quotes.
- `_resolve_tenant(tenant_id: str | None) -> str | None`: `""` becomes `None`, then the argument wins over `get_current_tenant()`. It never reads the payload.
- `_require_writable(row: LegalDocument | None, document_id: str, tenant: str | None) -> LegalDocument`: raises `StoreDocumentNotFoundError(f"Document not found: {document_id}")` when the row is `None` or `row.tenant_id != tenant`.
- `update_document`: resolve, `session.get(..., with_for_update=True)`, `_require_writable`, `apply_update`, commit.
- `save_document`: resolve, `session.get(..., with_for_update=True)`. `None` inserts with `tenant_id=tenant`. A foreign row raises. An owned row goes to `apply_update`. `document["id"]` is written only after the check passes. On insert, a payload `tenant_id` joins the dropped-key list.
- Both: `StaleDataError` on flush maps to `StoreDocumentNotFoundError`.

## Error flow
The check runs before any attribute write. On a raise, the session rolls back, so the row is unchanged.

## Fit
- T2, E1, E3, E5: met by `_resolve_tenant` and `_require_writable`.
- F1-F3, F7, F8: met.
- F4, F5: not handled (accepted, F5 kept by a test).

Effort: S.

## Risks
1. Race between check and write: closed by the row lock.
2. The guard lives in Python only. A future write path that skips the helper is unguarded. Mutation tests must keep the helper call alive.
