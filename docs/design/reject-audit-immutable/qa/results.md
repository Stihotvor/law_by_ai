# QA results: reject-audit-immutable

Basis: unit suite 1399 passed; Docker suite 1580 passed, 5 skipped, 0 failed (run by the main session). Counts: 33 pass, 1 partial, 0 fail, 3 not-automated.

P = tests/integration/test_rejected_document_privileges.py
R = tests/integration/test_reject_document.py
PR = tests/unit/core/security/test_principal.py
PG = tests/unit/plugins/test_postgres_reject.py
AP = tests/unit/ui/test_auth_principal.py

| Case | Status | Covered by |
|---|---|---|
| QA-001 | pass | P::test_app_role_is_denied[UPDATE] |
| QA-002 | pass | P::test_app_role_is_denied[DELETE] |
| QA-003 | pass | P::test_app_role_is_denied[TRUNCATE] |
| QA-004 | pass | P::test_app_role_keeps_insert_and_select |
| QA-005 | pass | P::test_app_role_keeps_insert_and_select |
| QA-006 | pass | test_rejected_document_privileges.py::test_sequence_grant_gives_distinct_ids |
| QA-007 | pass | test_rejected_document_privileges.py::test_owner_keeps_update_delete_truncate |
| QA-008 | pass | P::test_schema_guard_table_privilege_false[UPDATE/DELETE/TRUNCATE] |
| QA-009 | pass | P::test_schema_guard_no_column_update |
| QA-010 | pass | P::test_schema_guard_public_has_no_privilege |
| QA-011 | pass | test_rejected_document_privileges.py::test_existing_rows_survive_upgrade |
| QA-012 | pass | P::test_migration_round_trip |
| QA-013 | pass | test_rejected_document_privileges.py round trip asserts UPDATE/DELETE true and TRUNCATE false after downgrade |
| QA-014 | not-automated | OPEN: lock timeout not in requirements; needs two sessions and a timing check. Only the setting validation is tested (tests/unit/config/test_settings.py::test_migration_lock_timeout_rejects_invalid_value) |
| QA-015 | pass | test_rejected_document_privileges.py::test_repeated_upgrade_is_safe |
| QA-016 | pass | R::test_reject_refused_principal_writes_nothing[none]; PG::test_reject_without_principal_raises_before_db |
| QA-017 | pass | R::test_reject_refused_principal_writes_nothing[blank-email]; PR::test_blank_email_is_refused |
| QA-018 | pass | R::test_reject_refused_principal_writes_nothing[spaces-email] |
| QA-019 | pass | R::test_reject_refused_principal_writes_nothing[role-user]; PG::test_reject_non_admin_principal_raises_before_db |
| QA-020 | pass | R::test_reject_audit_actor_equals_principal_email[plain]; PG::test_reject_actor_comes_from_principal |
| QA-021 | pass | PG::test_reject_signature_has_no_admin_parameter |
| QA-022 | pass | R::test_reject_audit_actor_equals_principal_email[padded]; PR::test_admin_passes_with_stripped_email |
| QA-023 | pass | R::test_concurrent_rejects_write_one_audit_row_and_one_hook_call |
| QA-024 | pass | test_reject_document.py::test_reject_twice_raises_not_found_and_one_audit_row |
| QA-025 | pass | R::test_reject_unknown_id_raises_without_audit_or_hook; PG::test_reject_unknown_id_raises_and_writes_nothing |
| QA-026 | pass | test_reject_document.py::test_audit_insert_failure_keeps_document_and_writes_no_audit |
| QA-027 | pass | test_postgres_reject.py::test_reject_after_context_exit_is_refused |
| QA-028 | pass | test_principal.py::test_new_thread_does_not_inherit_principal |
| QA-029 | pass | test_postgres_reject.py::test_nested_context_restores_outer_actor |
| QA-030 | pass | AP::test_require_auth_sets_the_principal |
| QA-031 | pass | AP::test_sign_out_clears_the_principal |
| QA-032 | pass | AP::test_logout_button_clears_the_principal_before_rerun |
| QA-033 | pass | test_auth_principal.py::test_failed_login_sets_no_principal |
| QA-034 | not-automated | OPEN: the reject UI page is out of scope per decision.md |
| QA-035 | pass | Docker suite, 0 failed: test_fetch_rejection.py, test_fetch_worker_pool.py, test_fetch_task_integration.py, test_reject_document.py |
| QA-036 | not-automated | needs a throwaway migration in a test database to show the guard goes red; the guard tests exist (QA-008) |
| QA-037 | partial | quality gate: lint, format, types, security, tests and lock pass; audit not run locally (needs network, runs in CI); diff-cover 100%; Docker suite 1580 passed |

Counts: pass 33, partial 1, fail 0, not-automated 3.
