# Path 1: single source of truth

- New `src/data/autogen.py` with `AUTOGEN_COMPARE_OPTS = {"compare_server_default": True}`.
- `migrations/env.py` spreads it into both `context.configure` calls.
- Drift test passes `opts=AUTOGEN_COMPARE_OPTS` to `MigrationContext.configure`; asserts `diff == []`.
- New integration test: change the status server default on a copy of the metadata, assert at least 1 `modify_default` entry.
- `models.py`: `name=conv("ck_legal_document_status")` so any naming convention keeps the name.
- New unit test: a `MetaData` with a ck convention keeps the exact name.

Failure modes: one dict for env.py and the test; conv() pins the name; the drift test sees the diff list.
Not handled: a cast false positive (fixed by a comparator only if seen).
Effort: S. Main risk: conv() behaviour in DDL must match the plain string in migrations.
