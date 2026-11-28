# Review: procedure-kb

Verdict: PASS WITH WARNINGS (2026-11-27). Scope: `main..HEAD`, 14 commits.

## Layers
- Gate: ruff check, ruff format --check, pyright, bandit and unit tests pass (run by the main session with the main checkout venv, because the gate agent could not run tools in the worktree). Not run locally: pip-audit, mutation score, diff-cover (CI runs them).
- TDD order check: pass, no violation in the range.
- Database tests: run on a disposable PostgreSQL 18.6 with the project role script. Procedure files: 43 passed. Whole integration suite: 271 passed, 9 skipped (no Valkey, no live Sejm), 2 failed in `test_login_flow.py` (cookie fake of the login UI, no shared code with this change, to be confirmed on CI).
- Structure, security, style, performance: no critical or high finding.

## Findings fixed in this change
YAML size cap and duplicate-key check, strict `source_url` characters and length, attacker text kept out of error messages, `get` wraps a bad stored row in `ProcedureStoreError`, `lock_timeout` on save, seed script handles unreadable files and uses one clock, tri-state compare made explicit, duplicate sort removed, task ids removed from code.

## Findings kept as follow-ups
- `source_url` host allowlist (an owner decision: allowed domains).
- Rename the port method `list` (shadows the builtin).
- Step count and upload size limits belong to the upload page.
- QA-080: seed against a stopped server shows no password (no test yet).
- Writes are guarded in code only. The strategic fix is a `SECURITY DEFINER` import function.
- A draft or approval state for uploaded procedures.
