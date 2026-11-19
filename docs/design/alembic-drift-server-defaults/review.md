# Review

Gate: ruff check, ruff format, pyright, bandit, unit tests pass. `uv lock --check` passes. pip-audit could not reach the network here, CI runs it, and no dependency changed.

Verdicts: structure PASS WITH WARNINGS, security no findings, style no blockers.

Fixed:
- The tests pass a copy `dict(AUTOGEN_COMPARE_OPTS)` to Alembic, so Alembic cannot change the shared dict.
- The tests use `DocumentStatus` values, not string literals.
- The offline comment in `env.py` states why the options are passed.
- The `users` table assertion now checks the parametrized table and names the import it depends on.

Kept, with reason:
- `src/data/autogen.py` sits next to the models. The decision chose this place, and the module has no Alembic import.
- The parametrized test covers more than the decision listed (QA-008, QA-009). Each case is one more `modify_default` check.
- The `Base.metadata` unchanged assertion stays in the test. It is QA-010.
- `_status_default_arg` stays as a helper, because the type assertion needs a narrowing step.
