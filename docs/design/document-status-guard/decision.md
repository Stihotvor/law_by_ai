# Decision: document status guard

## Context
`save_document` and `update_document` accept a `status` from the caller, and `apply_update` writes any key that matches a model attribute. Any code path can approve a document without an admin check or an audit row. No migration may be added here, because the reject audit protection comes next in the same area.

## Options
- Path 1: write allowlist, ignore with warning. The generic paths copy only editable fields. `status` has no effect and a warning names the dropped key.
- Path 2: fail-fast contract. A `status` other than `needs_review` raises `ValueError` before a write. Other columns stay writable.

## Decision
Path 1, chosen by the owner at G1. The architect recommended it; the DBA marked both paths feasible.
- `apply_update` uses a fixed map from payload key to model attribute: `title`, `content`, `source`, `source_url`, `is_processed` map to the same name, `metadata` maps to `metadata_`, and `last_updated` goes through `parse_dt` to `last_updated`. It never calls `setattr` with a payload key. A unit test asserts that `row.metadata_` is set and `row.metadata` is still `Base.metadata`.
- `apply_update` returns the sorted names of the keys it dropped, except `id`. Dropped keys include `status`, `tenant_id` and unknown keys such as `foo`. Unknown keys were dropped silently before; they now appear in the warning on purpose.
- `save_document` inserts with `status = needs_review` as a constant. The insert reads `tenant_id` as today (parameter, then payload, then context).
- Every write path logs one warning per call that lists the dropped key names, never values: the upsert branch and `update_document` use the names from `apply_update`, and the insert branch warns when the payload has a `status` key.
- Unknown status values (`bogus`, `rejected`, empty, `None`) no longer raise `ValueError`. They are dropped with the warning, like any other status value.
- `validate_status` is removed, and the unused `DocumentStatus` import goes from `mappers.py`. `postgres.py` keeps `DocumentStatus` for the insert constant. The review issue adds its own approve path.
- `fetch.py` `_to_document` stops sending `status`, so a normal ingest logs no warning.
- The existing `ValueError` unit tests for `status` become unit tests of `apply_update` (no database) and integration tests of the store.

## Consequences
- A save that re-sends the id of an `approved` row keeps it `approved`, and a `needs_review` row cannot be approved through the generic paths. The fetch task sends no id, so each fetch inserts a new `needs_review` row.
- `tenant_id` and `id` can no longer change through upsert or update. This closes a move between tenants. No caller in `src/` uses that route today.
- Misuse does not raise. The warning log is the only signal.
- Raw SQL and code outside the store can still set `approved`. The database-level guard (trigger or role split) is a follow-up, planned with the reject audit protection.
- 0 migrations.
