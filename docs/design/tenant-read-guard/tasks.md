# Tasks: tenant read guard (path 1, accepted)

Gate before build: the `solution-architect` checks `contract.md` against the current code.

1. Check callers. Read each test caller listed in `contract.md`. Find each call that reads a tenant row with no tenant or with another tenant, or deletes a foreign or shared row as a tenant. Done when: the list is in the PR body, and each such test has a fix in task 4.
2. Write unit tests first in `tests/unit/plugins/test_postgres_tenant_guard.py`, with `FakeSession` from `tests/fakes/postgres_session.py`. Assert on the compiled SQL in `session.statements`:
   - With a tenant, `get_document`, `search_documents` and `get_recent_changes` send `tenant_id = :T OR tenant_id IS NULL`. With no tenant they send `tenant_id IS NULL`. None of them sends `IS NOT DISTINCT FROM`.
   - `delete_document` sends one `DELETE` with `tenant_id IS NOT DISTINCT FROM` and commits once.
   - The argument wins over the context. An argument `""` falls back to the context.
   - `search_documents` has the tenant filter before `LIMIT`.
   Done when: the tests fail on `main`.
3. Write integration tests first in `tests/integration/plugins/test_postgres_tenant_guard.py`, on the Docker PostgreSQL:
   - A tenant sees its own rows and shared rows, and not foreign rows, in `get_document`, `search_documents` and `get_recent_changes`.
   - `get_document` of a foreign id returns `None`, the same as a missing id.
   - A no-tenant caller sees only shared rows.
   - With `limit=1`, `search_documents` returns an own row when a newer foreign row exists.
   - A tenant cannot delete a shared row or a foreign row. All 10 `doc_to_dict` fields of the kept row stay unchanged. The call returns `None` with no error.
   - A tenant deletes its own row. A no-tenant caller deletes a shared row and cannot delete a tenant row.
   Done when: the tests fail on `main` for every case except "missing id returns None", "tenant sees shared rows", "tenant deletes own row" and "no-tenant caller deletes a shared row".
4. Add `_readable_by` and `_owned_by`. Use `_owned_by` in `_owned_row_for_update` and `delete_document`, and `_readable_by` in the three read calls (see `contract.md`). Update the four docstrings and state the guard limit. Fix the tests from task 1. Done when: the tests of tasks 2 and 3 pass, and the existing store tests pass.
5. Run the quality gate: ruff check, ruff format --check, pyright, `pytest -m "not integration"`, the Docker suite, and the coverage and mutation gates. Done when: all pass with no gate lowered.

Order: tasks 1, 2 and 3 in parallel, then 4, then 5.
Follow-ups: see "Out of scope / follow-ups" in `requirements.md`.
