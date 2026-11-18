# Requirements: tenant write guard

Scope: `PostgreSQLStore.save_document` and `PostgreSQLStore.update_document` in `src/plugins/relational_db/postgres.py`, and `mappers.apply_update`.
Out of scope: RLS on `legal_document`, tenant filters on read paths (`get_document`, `search_documents`, `get_recent_changes`) and on `delete_document`.

Source of facts: the code at commit `ba4286a` and the follow-ups in `docs/design/document-status-guard/review.md`.
The owner accepted every default below, and the dba changes, on 2026-11-18.

## Business Goals
- G1. A tenant cannot change or claim a document of another tenant through the store. This is a charter item ("tenant leak tests") for the MVP (planning date 2027-02-28).
- G2. A caller cannot learn that a document of another tenant exists from the update path. The answer for a foreign row is the same as for a missing row.
- G3. Close the two security follow-ups (medium) from the document status guard review before RLS work starts.

Decided: the store, not its callers, enforces the write rule.

## Technical Constraints
- T1. Python 3.13, SQLAlchemy 2.0 ORM, PostgreSQL. No new dependency. No schema change and no migration.
- T2. The tenant comes only from the `tenant_id` argument or `get_current_tenant()`. A payload `tenant_id` never picks the tenant. Rule: first change `""` to `None` in the argument, then `tenant = argument if argument is not None else get_current_tenant()`, then change `""` to `None` in the result.
- T3. Reuse the existing error type. `StoreDocumentNotFoundError` exists (base `LookupError`). `update_document` raises `KeyError` for a missing id today. Callers that catch `KeyError` must keep working.
- T4. `legal_document.tenant_id` is nullable. `NULL` means a shared document (charter: shared documents, per-tenant data).
- T5. Celery prefork workers do not carry the contextvar. They pass `tenant_id` as an argument (`core/security/tenant.py` note).
- T6. Quality gate: ruff check, ruff format --check, pyright, pytest. Integration tests run on the Docker PostgreSQL. Coverage and mutation gates as in CONTRIBUTING.md.
- T7. Both write paths load the row with `session.get(LegalDocument, id, with_for_update=True)`. The row lock holds until commit or rollback.

Decided: one ownership rule, applied in Python under a row lock, with the existing error.

## Edge Cases
- E1. Ownership rule: a caller can write a row only when `row.tenant_id` is equal to the caller tenant. `NULL` is equal to `NULL`.
  - E1a. Tenant caller and shared row (`NULL`): treated as foreign. Tenant admins cannot edit shared documents.
  - E1b. No-tenant caller (system, ETL) and tenant row: treated as foreign.
  - E1c. No-tenant caller insert: the new row is shared (`tenant_id` NULL). This is the current behaviour, and it stays.
  - E1d. A no-tenant caller can write every shared row. Caller RBAC (`admin` role, ADR-0013) is the only guard on this path until RLS exists.
- E2. Argument and context both set and different: the argument wins (T2).
- E3. Payload has `tenant_id` on insert: the store ignores it and logs the key name as dropped (same as upsert today).
- E4. `save_document` with a caller-chosen id that a foreign row owns: raise an error. Do not insert a new row with a new id. Do not overwrite.
- E5. Empty-string tenant (`""`) in the argument or in the context: the store treats it as `None` (T2). An argument `""` falls back to the context tenant. It never widens access beyond the context tenant.
- E6. Payload without `id`: the store makes a new UUID4. No foreign row can own it, so the call inserts.

Decided: foreign rows behave like missing rows on update, and the upsert of a foreign id raises.

## Failure Modes
- F1. Cross-tenant `update_document`: raise `StoreDocumentNotFoundError` with the text `Document not found: <id>`, the same as for a missing id. The row stays unchanged. No commit happens.
- F2. Cross-tenant `save_document` upsert: raise `StoreDocumentNotFoundError` with the same text. The row stays unchanged. The payload dict stays unchanged (no new `id`, no other key).
- F3. `StoreDocumentNotFoundError` must be caught by `except KeyError` (T3). Change its base to `KeyError`. `except LookupError` in `reject` callers keeps working, because `KeyError` is a `LookupError`.
- F4. Residual existence oracle on `save_document`: an unknown caller-chosen id inserts, a foreign id raises. The global primary key makes this unavoidable without RLS. The owner accepted this risk. Follow-up: server-generated ids only, so a caller cannot choose an id.
- F5. Race: two inserts of the same new id at the same time. `session.get` finds no row to lock, so both insert. The second raises `IntegrityError` from the database. This stays, and a test keeps it.
- F6. No log line contains the caller tenant, the row tenant or payload values. The warning names only dropped keys (existing rule).
- F7. `StaleDataError` on flush (the row changed or went away under the session): the store maps it to `StoreDocumentNotFoundError` with the same text. The session rolls back.
- F8. Race between ownership check and write: closed by the row lock (T7).

Decided: one error type (`StoreDocumentNotFoundError`, now a `KeyError`) for "no row you can write".

## Success Metrics
- M1. 100% of the QA cases pass (15 cases in `qa.md`), on the Docker PostgreSQL.
- M2. 0 changed columns on the foreign row after each failed call (the test compares all 10 `doc_to_dict` fields before and after).
- M3. Error text for a foreign id and a missing id is byte-equal in 100% of the update and upsert cases.
- M4. 0 regressions in the existing store tests (`pytest -m "not integration"` and the Docker integration suite).
- M5. Coverage and mutation scores on the changed lines meet the CONTRIBUTING.md gates (no gate lowered).
