# worker-189 QA results

Unit run: `.venv/bin/pytest -m "not integration"` -> 1244 passed, 95 deselected.
Docker integration suite (separate compose project, fresh volumes): 1334 passed, 5 skipped (4 need SEJM_LIVE_TEST=1, 1 needs the smoke worker). QA-010 is not among the skipped tests.
ruff/pyright: not needed, because this run changed no Python file.
No new tests written; all mappable cases are covered by existing tests.

U = tests/unit/tasks/test_fetch_close_store.py
I = tests/integration/tasks/test_fetch_close_store.py

| id | status | test file:line | note |
|----|--------|----------------|------|
| QA-001 | pass | U:42 | no store, factory not called |
| QA-002 | pass | U:49 | close once |
| QA-003 | pass | U:74 | rebuild after close (direct call, not via signal) |
| QA-004 | pass | U:58 | warning with exc_info, swallowed |
| QA-005 | pass | U:105 | fresh build after failed close |
| QA-006 | not-automated | - | SIGKILL timing and pg_stat_activity of a real child; no subprocess allowed |
| QA-007 | not-automated | - | needs DB one revision behind head plus a migration harness; not covered by an existing test (unit U:85 covers propagation only) |
| QA-008 | pass | U:114 | |
| QA-009 | pass | U:126 | |
| QA-010 | pass | I:37 | live PostgreSQL in the Docker suite |
| QA-011 | pass | U (whole file) | unit suite passes with no DB |
| QA-012 | pass | U:96 | signal sent with sender=None |
| QA-013 | pass | U:136 | |
| QA-014 | pass | U:153 | |
| QA-015 | pass | U:145 | |
| QA-016 | pass | U:172 | |
| QA-017 | not-automated | - | needs live DB role and statement log |
| QA-018 | not-automated | - | needs a real solo-pool worker (subprocess) |
| QA-019 | not-automated | - | needs a real prefork worker recycle |
| QA-020 | not-automated | - | needs real autoscale and DB connection counts |
| QA-021 | not-automated | - | coverage/mutation tooling run, outside this test run |
