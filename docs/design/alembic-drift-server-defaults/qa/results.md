# QA results

Run: Docker suite, project `law_by_ai-alembic-drift`, 1586 passed, 5 skipped. Targeted run: 26 passed.

| Case | Result | Evidence |
|---|---|---|
| QA-001 | pass | `test_autogenerate_detects_changed_server_default[status_changed]` |
| QA-002 | pass | `test_autogenerate_finds_no_changes` |
| QA-003 | pass | `test_check_name_survives_naming_convention` |
| QA-004 | pass | `git diff main -- migrations/versions` is empty |
| QA-005 | pass | `test_autogenerate_finds_no_changes` (0 diff with the cast) |
| QA-006 | pass | `test_autogenerate_finds_no_changes` (0 diff for `session_version`) |
| QA-007 | pass | `test_autogenerate_finds_no_changes` (columns with no default give 0 diff) |
| QA-008 | pass | `test_autogenerate_detects_changed_server_default[session_version_changed]` |
| QA-009 | pass | `test_autogenerate_detects_changed_server_default[status_removed]` |
| QA-010 | pass | Base.metadata assertion in the changed-default test |
| QA-011 | pass | Exactly 1 entry asserted, so no `remove_table` entry appears |
| QA-012 | partial | Each suite run checks once. Two full runs gave 0 diff, no in-test repeat |
| QA-013 | partial | `test_opts_only_enable_compare_server_default` and the shared import. The `env.py` spread is checked by review, not by a test |
| QA-014 | not-automated | Manual `alembic revision --autogenerate`. Covered in effect by QA-002 |
| QA-015 | not-automated | Offline mode is not run in tests. The change adds one keyword argument |
| QA-016 | pass | `test_check_constraint_definition_and_validated` (unchanged) |
| QA-017 | pass | `test_check_constraint_definition_and_validated` finds the name |
| QA-018 | pass | `test_status_check_constraint_lists_enum_values` |
| QA-019 | pass | `test_opts_only_enable_compare_server_default`, `test_module_does_not_import_alembic` |

Counts: 15 pass, 2 partial, 2 not-automated, 0 fail.
