# Requirements: procedure-kb

Source: the issue "Bureaucracy knowledge base: schema and 3 seed procedures". Facts come from `pyproject.toml`, `src/data/`, `docs/adr/0008-mvp-scope.md`, `docs/adr/0015-information-only-answers.md` and the issue "Bureaucracy assistant agent" (the consumer).

## Business Goals
- The bureaucracy assistant needs checked procedure data. A wrong step can harm a user (a missed deadline, a wrong office). Today no procedure data exists.
- Each step carries its source and the date a person last checked it. The user sees where a step comes from and how old it is.
- Three procedures ship first: PESEL, residence card, tax ID. The owner reviews every source and step before merge. A lawyer reviews before v1.
- Decided (owner, G1, 2026-11-27): there will be many procedures, and admins will add them at runtime by uploading YAML. So the data lives in the database, with a revision history. The upload page is a follow-up issue. This task delivers the module under it.
- Decided: the consumer is the bureaucracy assistant. It needs "find a procedure by slug" and a list call for a menu.
- Non-goals: the upload page (follow-up issue), auto-update of steps, more than the 3 seed procedures, a draft or approval state for uploads (OPEN, follow-up).

## Technical Constraints
- Python 3.13. `pydantic==2.14.2` and `pyyaml==6.0.3` are already dependencies. No new dependency.
- A separate module `src/core/procedures/` (pydantic models, YAML parser, import service, read calls). Seed content in `data/procedures/*.yaml`, loaded by `scripts/seed_db.py` (new). Tests in `tests/unit/` and `tests/integration/`.
- One import function takes YAML text and an actor, validates it, and writes it to the database. The seed script and the later upload page both call it.
- Tables `procedure`, `procedure_step` and `procedure_revision` (append-only), one Alembic migration. The tables are shared, with no `tenant_id` and no RLS. Writes need the admin principal.
- Step fields: `text`, `source_url`, `last_checked` (a date), and the line "verify with the office". A step with an empty `source_url`, an invalid date or no verify line fails validation.
- Exactly 3 seed procedures: PESEL, residence card, tax ID.
- Unit tests use no network. The `source_url` value is validated as an https URL by syntax only.
- Budget: 4-6 GB host. The data is small (3 files). The loader adds no service and no background thread.
- Wording follows ADR-0015: information, not advice. Only lawful procedures.
- `scripts/seed_db.py` is named by the issue but does not exist (checked 2026-11-27). This task creates it.
- The "date not in the future" rule lives in pydantic only (a SQL CHECK with `CURRENT_DATE` is not immutable). The clock is injectable for tests.

## Edge Cases
- A YAML file with an empty `source_url`, a missing `last_checked`, a date in the future, or no verify line: the import raises an error that names the file (or the upload) and the step. Nothing is written.
- A malformed YAML file or one with an unknown key: loading raises an error that names the file.
- Two seed files with the same slug: the seed stops and names both files. Importing a slug that exists adds a new revision and replaces the steps in one transaction.
- An import by a caller that is not an admin: `PrincipalRequiredError`. Nothing is written.
- An import of identical content: no new revision.
- Unknown slug: the find call returns a clear "not found" result. It does not raise a bare KeyError.
- An empty table: the list call returns an empty list.
- A procedure with zero steps fails validation.
- A `source_url` with a scheme other than https, or with credentials: validation fails.

## Failure Modes
- Bad data must never reach the assistant. The import validates before any write and runs in one transaction: a failure leaves the old data.
- History must survive. The app role cannot change or delete a revision row.
- A stale `last_checked` date is shown to the user. The system does not hide it. Auto-update is a non-goal.
- The owner gate is a process rule: an approving PR review from the owner before merge. A test cannot prove it. The PR text states it.
- A change to the step schema must not break the assistant silently. The schema has a version field and a test that pins the fields.

## Success Metrics
- 4 of 4 Gherkin scenarios of the issue pass: seed has exactly 3 procedures, every step is complete, bad data is rejected, the owner gate holds.
- 3 of 3 seed procedures import with 0 validation errors, and a second seed run adds no revision.
- Each import writes one revision row with the actor and the time. The app role cannot UPDATE or DELETE a revision row (privilege test).
- 3 of 3 seed procedures have at least 3 steps and every step has a source link.
- Line coverage of `src/core/procedures/` is 100 % in unit tests. Diff coverage meets the CONTRIBUTING.md gate.
- Quality gate: ruff check, ruff format --check, pyright, pytest all pass with 0 errors.
- `get_procedure` and `list_procedures` return in under 100 ms for the 3 seed procedures (integration test).
