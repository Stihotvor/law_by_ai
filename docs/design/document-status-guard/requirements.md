# Requirements: document status guard

## Business Goals
- An admin reviews every new legal document before users see it. Today any code that calls `save_document` or `update_document` can set `status` to `approved` and skip that review, with no admin check and no audit row.
- This change closes that path. The explicit approve method (admin check plus audit) belongs to the review issue and is out of scope here.

## Technical Constraints
- Python 3.13, SQLAlchemy 2, PostgreSQL. Code in `src/plugins/relational_db/postgres.py` (`save_document`, `update_document`) and `src/plugins/relational_db/mappers.py` (`apply_update`, `validate_status`).
- `legal_document.status` has the values `needs_review` and `approved` (CHECK `ck_legal_document_status`). Python default and server default are `needs_review`.
- The only producer today is the fetch task (`src/tasks/fetch.py`). It sends `status = needs_review`.
- No new migration, so the next migration (reject audit protection) does not have to fork from this one. A database-level guard is out of scope unless the chosen design needs it.
- No new dependency.

## Edge Cases
- Insert through `save_document` with no `status`: the row has `needs_review`.
- Insert through `save_document` with `status = approved`: the row has `needs_review`, or the call fails before any write. The chosen design picks one of the two.
- Upsert through `save_document` of an existing `approved` row with `status = needs_review` or `approved`: the stored status does not change.
- `update_document` with `status` (any value, valid or not) and other fields: the stored status does not change.
- A `status` value that is not a known value (`bogus`, `rejected`, empty, `None`): the store must not write it. Existing tests expect `ValueError` for these values, and the design states whether that stays.
- The caller's input dict is not changed by the guard. Exception: `save_document` still writes a generated `id` back into the dict (current contract).

## Failure Modes
- If the design rejects `status`, the error is a `ValueError` raised before the store opens a session, and no row changes.
- If the design ignores `status`, the store logs nothing secret and the call succeeds with the status unchanged.
- The fetch task keeps working: an ingest saves the row as `needs_review` and returns `saved`.
- `get_document` and the other read paths still return `status`.

## Success Metrics
- 1 integration test: `update_document(doc_id, {"status": "approved", "title": "x"})` on a `needs_review` row leaves `status = needs_review` (or raises before any write, per design). 0 status changes.
- 1 integration test: `save_document` of a new payload with `status = approved` stores `needs_review` (or raises, per design).
- 1 integration test: an upsert through `save_document` does not change the status of an existing row.
- 1 integration test: the fetch task stores a new row as `needs_review` and logs no status warning.
- 0 new migrations in `migrations/versions/`.
- Quality gate: ruff check, ruff format --check, pyright and pytest pass. Coverage and mutation gates of CONTRIBUTING.md pass.
