# QA results: document status guard

Docker suite on this tree: 1431 passed, 6 skipped, 0 failed. Verdicts below come from mapping cases to existing tests (no new tests written, no product code edited).

Files (abbreviations):
- U = /home/yevhend/claude-projects/law_by_ai/tests/unit/plugins/test_postgres_status.py
- G = /home/yevhend/claude-projects/law_by_ai/tests/integration/plugins/test_postgres_status_guard.py
- FI = /home/yevhend/claude-projects/law_by_ai/tests/integration/test_fetch_task_integration.py
- FU = /home/yevhend/claude-projects/law_by_ai/tests/unit/test_fetch_task.py
- PG = /home/yevhend/claude-projects/law_by_ai/tests/integration/plugins/test_postgres.py

| Case | Verdict | Covering test(s) / note |
|---|---|---|
| QA-001 | pass | G test_update_cannot_change_status |
| QA-002 | pass | G test_insert_ignores_status |
| QA-003 | pass | G test_insert_without_status_logs_no_warning |
| QA-004 | pass | G test_upsert_keeps_stored_status[needs_review] |
| QA-005 | pass | G test_upsert_keeps_stored_status[approved] (row count not asserted) |
| QA-006 | pass | G test_upsert_cannot_approve_needs_review_row (Docker suite, 1443 passed) |
| QA-007 | pass | G test_unknown_status_does_not_raise["bogus"] |
| QA-008 | pass | G test_unknown_status_does_not_raise["rejected"] |
| QA-009 | pass | G test_unknown_status_does_not_raise[""] |
| QA-010 | pass | G test_unknown_status_does_not_raise[None] |
| QA-011 | pass | G test_insert_with_bogus_status_stores_needs_review (Docker suite, 1443 passed) |
| QA-012 | pass | G test_warning_names_keys_not_values |
| QA-013 | pass | G test_insert_ignores_status |
| QA-014 | pass | G test_upsert_warning_names_status (Docker suite, 1443 passed) |
| QA-015 | pass | G test_title_only_update_logs_no_warning (Docker suite, 1443 passed) |
| QA-016 | pass | G test_update_keeps_tenant_and_warns (Docker suite, 1443 passed) |
| QA-017 | pass | G test_upsert_keeps_tenant (Docker suite, 1443 passed) |
| QA-018 | pass | G test_update_keeps_row_id (Docker suite, 1443 passed) |
| QA-019 | pass | PG test_save_and_get_roundtrip (tenant-7) with G test_insert_ignores_status |
| QA-020 | pass | G test_update_metadata_round_trips (Docker suite, 1443 passed) |
| QA-021 | pass | U test_apply_update_copies_allowed_keys (metadata_ and Base.metadata) |
| QA-022 | pass | U test_apply_update_copies_allowed_keys |
| QA-023 | pass | U test_apply_update_drops_status |
| QA-024 | pass | U test_apply_update_drops_tenant_id_and_unknown_keys |
| QA-025 | pass | U test_apply_update_ignores_id_without_reporting_it |
| QA-026 | pass | U test_apply_update_drops_any_status_value |
| QA-027 | pass | U test_apply_update_does_not_mutate_input |
| QA-028 | pass | G test_save_without_id_ignores_approved_status (Docker suite, 1443 passed) |
| QA-029 | pass | G test_reads_still_return_status |
| QA-030 | pass | G test_update_missing_id_raises_and_creates_no_row (Docker suite, 1443 passed) |
| QA-031 | pass | G test_each_update_with_status_logs_one_warning (Docker suite, 1443 passed) |
| QA-032 | pass | FI test_task_saves_fetched_document, test_task_ingest_sends_no_status_and_stores_needs_review |
| QA-033 | pass | FI test_task_ingest_sends_no_status_and_stores_needs_review |
| QA-034 | pass | FU test_saved_document_fields (exact dict), FI test_task_ingest_sends_no_status_and_stores_needs_review |
| QA-035 | partial | Store-level upsert keep-approved is covered (G test_upsert_keeps_stored_status); a fetch always inserts a new row (no id), so no second-fetch test |
| QA-036 | pass | G test_validate_status_gone_and_no_new_migration (git status of migrations/versions) |
| QA-037 | pass | G test_validate_status_gone_and_no_new_migration |
| QA-038 | NOT AUTOMATED | Whole-suite quality gate (ruff, pyright, coverage, mutation); not a test |
| QA-039 | NOT AUTOMATED | Known open gap (DB-level guard is a follow-up); owner-role SQL in G fixtures incidentally shows the write works |

Counts: pass 36, partial 1, fail 0, not automated 2 (total 39). Docker suite after the review fix round: 1443 passed, 5 skipped, 0 failed.
