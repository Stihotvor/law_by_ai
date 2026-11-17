# Path 1: write allowlist, silent ignore

- `mappers.apply_update` copies only an allowlist: `title`, `content`, `source`, `source_url`, `is_processed`, `metadata`, `last_updated`. It skips `id`, `status` and every other key.
- `save_document` inserts with `status=needs_review` as a constant and never reads the payload `status`. The upsert branch uses the allowlist.
- `update_document` drops its status check. A `status` key has no effect.
- `validate_status` loses its last caller. Delete it, or keep it for the review issue.
- Existing `ValueError` tests in `tests/unit/plugins/test_postgres_status.py` become "status is ignored" tests.
- Closes the general `setattr` route too (any model column could be written).
- Effort: S. Risks: misuse is silent; the allowlist can drop a field a caller needs (for example `tenant_id`); the future approve method needs its own write path.
