# Path 2: fail-fast contract

- New `mappers.guard_status(document, *, allow_initial)`, called before any session. On save, a payload `status` other than `needs_review` raises `ValueError`. On update, any `status` key raises `ValueError`. Unknown values keep the existing `ValueError`.
- `save_document` inserts `needs_review` as a constant. The upsert branch skips `status`, so an `approved` row is not demoted by a re-ingest.
- `apply_update` skips `status` as defence in depth. Other `hasattr` keys still pass.
- Fetch task needs no change: it sends `needs_review`. A patched payload with `approved` makes the task fail with `ValueError`.
- Existing `ValueError` tests for unknown values keep passing.
- Effort: S. Risks: callers that send `status` on update start to fail, even with `needs_review`; the future approve method needs its own write path.
