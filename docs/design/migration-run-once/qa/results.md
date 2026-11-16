# QA results: migration run once

Test file: /home/yevhend/claude-projects/law_by_ai/tests/integration/test_migration_lock.py (4 tests).
Docker suite (main session, 2026-11-16): 1391 passed, 5 skipped, 0 failed. All 4 lock tests passed.
Local gate: ruff, ruff format, pyright, 1296 unit tests pass.

| Case | Status | Evidence | Reason (partial / not-automated) |
|------|--------|----------|----------------------------------|
| QA-001 | pass | test_concurrent_upgrades_apply_once: both exit 0, `alembic_version` rows == [head] | |
| QA-002 | pass | test_upgrade_blocks_while_lock_held: pg_locks shows ungranted key, process still running | Waits for the waiter in pg_locks, not a fixed 2 s; same intent |
| QA-003 | partial | test_upgrade_blocks_while_lock_held: exit 0 after release | Does not assert `alembic_version` is at head after the run |
| QA-004 | not-automated | none | No test runs upgrade on a database at head or counts advisory locks in pg_locks |
| QA-005 | not-automated | none | Only 2 concurrent runs are tested, not 3 |
| QA-006 | not-automated | none | No test checks the second run applies nothing or that the log has no "already exists" |
| QA-007 | partial | test_failed_upgrade_releases_lock: non-zero exit, bad revision named, pg_try_advisory_lock true, head upgrade then works | Failure is an unknown revision, not a migration that raises; no rollback assert; no pg_locks count |
| QA-008 | not-automated | none | No test makes run A fail while run B waits |
| QA-009 | not-automated | none | No test breaks the connection before unlock |
| QA-010 | not-automated | none | No SIGKILL test |
| QA-011 | not-automated | none | No 30 s wait test |
| QA-012 | not-automated | none | No lock_timeout test |
| QA-013 | not-automated | none | No repeated-run test |
| QA-014 | partial | test_offline_sql_ignores_held_lock: `--sql` exits 0 and prints CREATE TABLE | Database is reachable (not a closed port); first revision only; does not assert the script has no `pg_advisory_lock` |
| QA-015 | partial | test_offline_sql_ignores_held_lock: exit 0 while key held | No 2 s bound (30 s limit); first revision only, since `--sql` to head is unsupported (pre-existing) |
| QA-016 | not-automated | none | No test holds a different key |
| QA-017 | partial | Every lock test runs as `lawbyai_owner` on a scratch DB and exits 0 | Implicit only; no test asserts the absence of a permission error |
| QA-018 | not-automated | none | No schema comparison test; no new revision file was added (git status shows only env.py and docs changed) |
| QA-019 | pass | Checked by reading /home/yevhend/claude-projects/law_by_ai/docs/migrations.md "Overlapping upgrade runs": names 0x6C61775F6D6967, says no time limit, warns lock_timeout / statement_timeout fail the waiting run | Manual check, no test |
| QA-020 | pass | Local gate and Docker suite as above, 0 failures | Lock tests: 4 PASSED, not 3 as the case states |

Counts: pass 4, partial 5, fail 0, not-automated 11.
