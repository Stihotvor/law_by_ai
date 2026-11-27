# Decision: procedure knowledge base in the database

## Context
The bureaucracy assistant needs checked procedure data. Today there is none. The owner expects many procedures, added at runtime by admins who upload YAML, and wants the history of each change (2026-11-27). The first draft was a read-only YAML loader. The architect and the DBA judged that fine for 3 static files. The owner's scale and runtime-upload goal changed the choice.

## Options
- Path 1: reviewed YAML files in the repo, loaded into memory. No database. Effort S.
- Path 2: shared PostgreSQL tables, filled by a seed script. Effort M.
- Path 2, extended (chosen): path 2 plus one import function for runtime uploads and an append-only revision table.

## Decision
Path 2, extended. The owner chose the database and a YAML upload by the admin UI. The UI page is a follow-up issue.

### Module
Layering follows `src/core/users/` and ADR-0014. `core/procedures/` holds no SQL. The SQL adapter is a direct integration beside `PostgreSQLStore`. It is not a method of that class, because procedures are a separate aggregate and the class is already large.

In `src/core/procedures/` (imports only `core.security` and its own modules):
- `models.py`: frozen pydantic `Step` and `Procedure` with `extra="forbid"`.
  - `Step`: `key` (stable id inside the procedure, kebab-case), `text`, `source_url` (https, no credentials), `last_checked` (a date, not in the future), `verify_with_office` (non-empty).
  - `Procedure`: `schema_version`, `slug`, `title`, `steps` (at least 1, unique `key`, sorted by position), `revision` (set by the repository on read, not part of the YAML).
  - `ProcedureSummary`: `slug`, `title`.
  - `ImportResult`: `slug`, `revision`, `changed: bool`.
- `errors.py`: `ProcedureValidationError(source, step_key, reason)` and `ProcedureStoreError`.
- `parse.py`: `parse_procedure_yaml(text, today) -> Procedure`. The clock is a parameter.
- `ports.py`: the `ProcedureRepository` Protocol (`save(procedure, actor) -> ImportResult`, `get(slug)`, `list()`).
- `service.py`: `ProcedureService(repository)`.
  - `import_procedure(text) -> ImportResult`. It calls `require_admin_principal()` first, before any session opens, and takes the actor from the principal. It parses, then calls `repository.save`.
  - `get_procedure(slug) -> Procedure | None`. `None` means not found. A malformed slug also returns `None`.
  - `list_procedures() -> list[ProcedureSummary]`, sorted by slug.
  - Errors: `ProcedureValidationError` for bad input, `PrincipalRequiredError` for a non-admin, `ProcedureStoreError` for a database failure (the cause is chained, and the message holds no content).

In `src/plugins/relational_db/procedures.py`: `PostgresProcedureRepository(engine)`. Each call opens its own session. Reads return frozen pydantic objects, so no lazy load happens after the session closes. A `UNIQUE(procedure_id, revision)` IntegrityError maps to `ProcedureStoreError`. The ORM tables sit in `src/data/models.py`, next to `Base`.

Citation rule for the bureaucracy assistant: a curated step has no confidence score. The assistant cites a step by `slug`, `key` and `revision`, with its `source_url` and `last_checked`. It is not a retrieved chunk.

Identical content: compare `procedure.model_dump(mode="json", exclude={"revision"})` with the `content` of the latest revision (jsonb equality). The actor does not count. If equal, write nothing and return `changed=False`. The first import is revision 1.

Seed actor: the seed runs inside `principal_context(RequestPrincipal(email="system:seed", role=ADMIN))`.

### Data
One Alembic migration after head `c4a91e7f2b58`. Every column is NOT NULL. The migration sets `SET LOCAL lock_timeout = '5s'` in upgrade and downgrade. The downgrade stops when `procedure_revision` holds rows. Names are frozen literals. Server: PostgreSQL 18.
- `procedure`: `id` BIGINT GENERATED ALWAYS AS IDENTITY, `slug` unique, `title`, `schema_version`, `revision`, `updated_at` timestamptz default now(). CHECKs: `slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'`, `btrim(title) <> ''`, `revision >= 1`, `schema_version >= 1`.
- `procedure_step`: PK `(procedure_id, position)`. `procedure_id` FK ON DELETE CASCADE, `key`, `text`, `source_url`, `last_checked` DATE, `verify_with_office`. `UNIQUE(procedure_id, key)`. CHECKs: `position >= 0`, `key` kebab-case, non-empty text and verify line, `source_url LIKE 'https://%'`.
- `procedure_revision`: append-only. `id` identity, `procedure_id` FK ON DELETE RESTRICT (a cascade would bypass the append-only rule), `revision >= 1`, `content` JSONB with CHECK `jsonb_typeof(content) = 'object'`, `actor` (non-empty), `created_at` timestamptz default now(). `UNIQUE(procedure_id, revision)`.
- `content` is `Procedure.model_dump(mode="json", exclude={"revision"})`. It is the only full history, because steps are replaced.
- No `tenant_id` and no RLS (shared reference data).
- Grants to `lawbyai_app`, explicit, TRUNCATE revoked:
  - `procedure`: SELECT, INSERT, UPDATE. No DELETE, because no import deletes a procedure.
  - `procedure_step`: SELECT, INSERT, UPDATE, DELETE.
  - `procedure_revision`: SELECT, INSERT.
- The ORM tables are in `src/data/models.py` on the same `Base` that `migrations/env.py` reads, so autogenerate sees them.

### Import order
One READ COMMITTED transaction, in this order:
1. `INSERT ... ON CONFLICT (slug) DO UPDATE SET slug = EXCLUDED.slug RETURNING id, revision`. This locks the row, also for a new slug.
2. Compare the new `content` with the latest revision row (jsonb equality). If equal, roll back and return "unchanged". Do not touch `updated_at`.
3. Delete the steps of the procedure and insert the new steps.
4. `UPDATE procedure SET revision = revision + 1`, then insert the revision row.

Reads: `get_procedure` reads the procedure and its steps in one statement (join), so a reader never mixes an old title with new steps.

### Seed
`scripts/seed_db.py` reads `data/procedures/*.yaml` (3 files: PESEL, residence card, tax ID). It runs as `lawbyai_app` (`POSTGRES_URL`) inside `principal_context(RequestPrincipal("system:seed", ADMIN))` and calls `import_procedure`. Git keeps the history of the seed content. The revision table keeps the history of runtime changes. The seed is idempotent. Run order: migrate, then seed. `docs/migrations.md` states it.

### Follow-up issues
- Admin upload page in Streamlit (calls `ProcedureService.import_procedure`).
- Draft and approval state for uploaded procedures (OPEN: today an admin upload is live at once).

## Consequences
- Many procedures and runtime upload are possible, with one rule set (pydantic) and the DB constraints as a second guard.
- History is kept twice: Git for the seed files and revision rows for runtime edits.
- Known limit: writes are guarded by RBAC in code only. Any app code path, including the Celery worker, can write. Every write leaves a revision row. The strategic fix is a follow-up: a `SECURITY DEFINER` import function, with the app limited to SELECT and EXECUTE (as `public.auth_lookup_user`).
- Cost: a migration, a seed step in deploy, and drift if the seed is not rerun. A rerun is safe because the seed is idempotent.
- The issue text changes: it drops "seed in `scripts/seed_db.py` (exists)", sets the new files, and gets a Contract section for the bureaucracy assistant.
