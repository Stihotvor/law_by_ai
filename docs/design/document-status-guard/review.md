# Review: document status guard

Verdict: PASS WITH WARNINGS. Range `main..fix/document-status-guard`, 7 code files.

## Layer 1 gate
- ruff check, ruff format --check, pyright, bandit, unit tests, uv lock --check: pass.
- TDD order: pass.
- NOT RUN locally: pip-audit (needs network), diff-cover and mutation (CI runs them).

## Fixed in the review round
- Style and structure: the seven setter functions became one fixed key-to-attribute map.
- Security (low): the warning logs the id and key names with `%r`, so a key cannot forge a log line.
- Style (high, confirmed as a docstring error): the `save_document` docstring now states that the insert branch reports only `status`, and that a payload `tenant_id` still picks the tenant on insert.
- Structure (medium): the migration and `validate_status` checks left the integration file. A unit test checks that `validate_status` is gone.
- QA: 11 partial cases got integration tests.

## Kept, with reason
- `row.metadata is Base.metadata` assertion: the design requires proof that a payload key never shadows `Base.metadata`.
- Insert branch reads `tenant_id` from the payload (security, medium): the decision keeps the current insert rule. Follow-up: take the tenant only from the argument or the context.
- Existing-row writes do not filter by tenant (security, medium): this code predates the change, and `legal_document` has no RLS yet. Follow-up with the RLS work.
- Allowlist setters check no types (security, low): a wrong type fails at commit as a database error, with no integrity break.
- No database-level guard: the decision defers it to the reject audit protection work.
