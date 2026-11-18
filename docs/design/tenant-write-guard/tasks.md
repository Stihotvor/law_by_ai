# Tasks: tenant write guard (path 1, accepted)

Gate before build: the `solution-architect` checks `contract.md` against the current code.

1. Find callers. List every call of `save_document` and `update_document`, and every `except KeyError` or `except LookupError` around them, in `src/`, `scripts/` and `tests/`. Done when: the list is in the PR body, and each caller that relies on a payload `tenant_id` has a fix in task 4.
2. Write tests first for QA-1 to QA-15 in `qa.md`, as integration tests on the Docker PostgreSQL. Done when: the new tests fail on `main` for every case except QA-8, QA-9, QA-10 and QA-14 (current behaviour already passes them).
3. Change the error. `StoreDocumentNotFoundError` gets base `KeyError` and a plain `__str__`. Done when: QA-12 and the existing `reject` tests pass.
4. Add `_resolve_tenant` (with `""` to `None`) and `_require_writable`. In `save_document` and `update_document`, load with `with_for_update=True`, apply the helpers, and map `StaleDataError` on flush to `StoreDocumentNotFoundError`. Drop and log a payload `tenant_id` on insert. Update both docstrings, and state the shared-row guard limit. Fix the callers from task 1. Done when: QA-1 to QA-15 pass.
5. Run the quality gate: ruff check, ruff format --check, pyright, `pytest -m "not integration"`, the Docker suite, and the coverage and mutation gates. Done when: all pass with no gate lowered.

Order: tasks 1 and 2 in parallel, then 3, then 4, then 5.
Follow-up (separate issue): server-generated ids only, so a caller cannot choose a document id.
