# Requirements: Alembic drift test compares server defaults

## Business Goals
- The drift test must catch a model server default that differs from the database. Today a changed default passes silently, and a fresh database then gets a different default than the model promises.
- The CHECK constraint `ck_legal_document_status` must keep its exact name, because migrations and tests reference it by name.

## Technical Constraints
- Alembic 1.20.1. `MigrationContext.configure(opts={"compare_server_default": True})` turns the comparison on (`alembic/runtime/migration.py:179`).
- `migrations/env.py` must pass `compare_server_default=True` in both online and offline `context.configure` calls, so `alembic revision --autogenerate` and the test use the same rule.
- The test must use the same option source as `env.py`, so the two cannot drift apart.
- Server defaults today: `legal_document.status = 'needs_review'`, `users.session_version = 0`.
- Alembic 1.20.1 does not compare CHECK constraints by default. Name-based CHECK detection needs the opt-in `checkconstraint_byname` plugin, which this change does not enable. The `pg_get_constraintdef` test stays as the guard of the CHECK text.
- No new dependency. No schema change unless the comparison shows real drift.

## Edge Cases
- PostgreSQL renders defaults with casts (`'needs_review'::character varying`). Alembic must not report this as drift.
- A future `naming_convention` with a `%(constraint_name)s` ck token would rename the CHECK to `ck_legal_document_ck_legal_document_status`.
- A model with no server default and a database column with none must give no diff.

## Failure Modes
- If the comparison gives a false positive, the drift test fails on a clean tree. Fix: a custom comparator only if a real false positive appears.
- If someone adds a naming convention, the constraint name changes and a unit test must fail with a clear message.
- If `env.py` and the test use different options, drift found by one is hidden by the other.

## Success Metrics
- 1 new integration test: a changed model server default gives a non-empty diff (at least 1 `modify_default` entry).
- The existing drift test gives 0 diff entries on the current migrations.
- 1 unit test fails when the CHECK name in metadata is not exactly `ck_legal_document_status`.
- 0 changes to existing migration files.
