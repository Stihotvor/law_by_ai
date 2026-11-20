# QA results: admin-user-management

Run note: the test-engineer could not run pytest (hook). The orchestrator ran the full unit suite on
commit ff3498d: 1574 passed, 0 failed, 206 integration tests deselected. Ruff, format, pyright and
bandit are clean. Diff coverage is 95%. Rows below come from a static mapping of cases to tests.
UNIT-UNRUN means "covered by a unit test of that suite run, not run one by one here".
INT-UNRUN = covered only by an integration test. It needs Postgres and awaits CI. It has never run.
PARTIAL = covered in part. NO TEST = no test found.

Paths: U = tests/unit, I = tests/integration (under the worktree root).

| Case | Status | Test(s) |
|---|---|---|
| QA-001 | INT-UNRUN | I/test_user_service.py::test_created_user_logs_in |
| QA-002 | INT-UNRUN | I/test_user_service.py::test_deactivated_user_is_refused |
| QA-003 | INT-UNRUN + UNIT-UNRUN | I/test_user_service.py::test_deactivated_user_is_refused; I/test_store_deactivate.py::test_deactivate_changes_session_version; U/plugins/test_postgres_deactivate_port.py::test_update_is_tenant_scoped_and_only_flips_is_active |
| QA-004 | UNIT-UNRUN | U/ui/test_users_page.py::test_form_has_no_tenant_field; U/plugins/test_postgres_users_port.py::test_insert_writes_active_user_in_current_tenant |
| QA-005 | UNIT-UNRUN + INT-UNRUN | U/plugins/test_postgres_users_port.py::test_list_users_filters_tenant_orders_by_email_and_hides_hash; I/test_store_users.py::test_list_shows_no_foreign_rows |
| QA-006 | UNIT-UNRUN | U/plugins/test_postgres_users_port.py::test_user_to_record_has_no_hash_or_session_version; U/ui/test_users_page.py::test_table_never_shows_password_hash |
| QA-007 | UNIT-UNRUN + INT-UNRUN | U/ui/test_users_page.py::test_duplicate_email_shows_fixed_message; U/plugins/test_postgres_users_port.py::test_insert_duplicate_email_maps_to_refused; I/test_user_service.py::test_duplicate_email_same_error_in_any_tenant |
| QA-008 | UNIT-UNRUN + INT-UNRUN | same as QA-007; I/test_store_users.py::test_insert_duplicate_email_same_error_in_any_tenant |
| QA-009 | PARTIAL (UNIT-UNRUN) | U/core/users/test_service.py::test_email_normalised_and_password_hashed (normalisation only; no test of duplicate by case/space) |
| QA-010 | UNIT-UNRUN | U/core/users/test_service.py::test_email_normalised_and_password_hashed |
| QA-011 | UNIT-UNRUN | U/core/users/test_service.py::test_invalid_input_refused[email ""/"   "] |
| QA-012 | UNIT-UNRUN | test_invalid_input_refused[no-at.pl / a@@x.pl] |
| QA-013 | UNIT-UNRUN | test_invalid_input_refused (257 chars); test_limits_are_inclusive (256) |
| QA-014 | UNIT-UNRUN | test_invalid_input_refused (name 257); test_limits_are_inclusive (256) |
| QA-015 | UNIT-UNRUN | test_invalid_input_refused[password 11 chars]; test_password_rule_names_the_limits |
| QA-016 | PARTIAL (UNIT-UNRUN) | test_limits_are_inclusive[password 12] (creation only; no login with it) |
| QA-017 | PARTIAL (UNIT-UNRUN) | test_invalid_input_refused / test_limits_are_inclusive are multibyte-based; U/test_passwords.py::test_password_limits_live_in_core (12 and 72). No explicit 72/73 ASCII case |
| QA-018 | UNIT-UNRUN | test_invalid_input_refused[ą*36+p] (73 bytes); test_limits_are_inclusive[ą*36] (72 bytes) |
| QA-019 | UNIT-UNRUN + INT-UNRUN | test_invalid_input_refused[role root/""]; I/test_user_service.py::test_role_outside_valid_roles_is_refused |
| QA-020 | PARTIAL (UNIT-UNRUN) | test_admin_role_is_accepted; U/ui/test_users_page.py::test_create_calls_service_and_shows_success. No login-as-henry test |
| QA-021 | INT-UNRUN + UNIT-UNRUN | I/test_store_deactivate.py::test_already_inactive_is_noop_without_bump; U/plugins/test_postgres_deactivate_port.py::test_update_of_zero_rows_returns_false |
| QA-022 | INT-UNRUN + UNIT-UNRUN | I/test_store_deactivate.py::test_foreign_or_unknown_id_is_not_found; U/.../test_postgres_deactivate_port.py::test_missing_or_foreign_target_raises_not_found |
| QA-023 | INT-UNRUN + UNIT-UNRUN | same as QA-022; U/ui/test_users_page.py::test_deactivate_errors_show_fixed_messages[not found] |
| QA-024 | INT-UNRUN + UNIT-UNRUN | I/test_store_deactivate.py::test_self_deactivation_is_refused; U/.../test_postgres_deactivate_port.py::test_self_raises_before_any_lock |
| QA-025 | INT-UNRUN + UNIT-UNRUN | I/test_store_deactivate.py::test_two_sessions_race_keeps_one_admin; U/.../test_sole_admin_target_raises_last_admin |
| QA-026 | INT-UNRUN + UNIT-UNRUN | I/test_store_deactivate.py::test_last_admin_is_refused (first step); U/.../test_admin_target_locks_admin_set_first_without_limit |
| QA-027 | UNIT-UNRUN + INT-UNRUN | U/.../test_self_raises_before_any_lock; I/test_store_deactivate.py::test_self_deactivation_is_refused |
| QA-028 | INT-UNRUN | I/test_store_deactivate.py::test_two_sessions_race_keeps_one_admin |
| QA-029 | UNIT-UNRUN | U/ui/test_users_page.py::test_non_admin_sees_admin_required_and_service_is_not_called |
| QA-030 | UNIT-UNRUN + INT-UNRUN | U/core/users/test_service.py::test_role_user_is_refused[create]; I/test_user_service.py::test_role_user_changes_nothing |
| QA-031 | UNIT-UNRUN + INT-UNRUN | test_role_user_is_refused[deactivate]; I/test_role_user_changes_nothing |
| QA-032 | UNIT-UNRUN | U/ui/test_users_page.py::test_demoted_session_cannot_create / _deactivate; U/core/users/test_service.py::test_actor_not_active_admin |
| QA-033 | UNIT-UNRUN | test_actor_not_active_admin |
| QA-034 | UNIT-UNRUN + INT-UNRUN | U/.../test_missing_or_foreign_target_raises_not_found; I/test_foreign_or_unknown_id_is_not_found (admin of A on B id; not literally B-admin on A id) |
| QA-035 | UNIT-UNRUN | test_empty_tenant_refused_before_port |
| QA-036 | UNIT-UNRUN + INT-UNRUN | U/plugins: test_insert_without_tenant_raises_before_any_sql, test_list_users_without_tenant_returns_empty, test_no_tenant_raises_before_any_sql; I/test_store_users.py::test_no_tenant_*; I/test_store_deactivate.py::test_no_tenant_changes_nothing |
| QA-037 | INT-UNRUN + UNIT-UNRUN | I/test_store_users.py::test_list_shows_no_foreign_rows; U/.../test_insert_writes_active_user_in_current_tenant |
| QA-038 | UNIT-UNRUN | U/ui/test_users_page.py::test_create_db_error_shows_generic_message_without_raw_text; U/plugins test_insert_operational_error_propagates_and_rolls_back |
| QA-039 | UNIT-UNRUN | test_deactivate_errors_show_fixed_messages[OperationalError]; test_db_error_propagates_and_rolls_back |
| QA-040 | PARTIAL (UNIT-UNRUN + INT-UNRUN) | U/plugins test_insert_other_integrity_errors_are_not_mapped; I/test_insert_other_integrity_error_is_not_mapped. No UI-level test that the page shows the generic error for it |
| QA-041 | PARTIAL (UNIT-UNRUN) | U/core/users/test_service.py::test_logs_hold_no_password_or_hash (success path only); test_create_refusal_log_holds_no_email_or_password; U/ui test_db_error_logs_only_the_class_name |
| QA-042 | UNIT-UNRUN | test_audit_holds_actor_target_and_change |
| QA-043 | UNIT-UNRUN | test_audit_holds_actor_target_and_change (changed False) |
| QA-044 | NO TEST | no change to the login code path. Existing tests/unit/test_ui_auth.py cover it |
| QA-045 | PARTIAL (UNIT-UNRUN) | service refusals: test_invalid_input_refused; UI fixed messages: test_duplicate_email_shows_fixed_message. No UI test submits each invalid input |
| QA-046 | INT-UNRUN | I/test_user_service.py::test_each_action_under_one_second (seeds 1 admin, not 100 users) |
| QA-047 | UNIT-UNRUN | U/ui/test_users_page.py::test_duplicate_email_shows_fixed_message (no test of two successive submits) |
| QA-048 | UNIT-UNRUN + INT-UNRUN | test_role_user_is_refused[create]; I/test_role_user_changes_nothing (self-promote attempt) |
| QA-049 | UNIT-UNRUN | U/core/users/test_port_conformance.py (store and fake repo match the port, drift is detected) |
| QA-050 | CHECKED BY GATE | diff-cover 95% (gate 90%), repo coverage 98.7% (gate 88%). The mutation gate is scoped to src/agents/fetch and does not apply |
| QA-051 | UNIT-UNRUN | create_user signature unchanged (store keeps its signature). Existing tests/unit/bootstrap init_stack tests cover the seed path |

Counts: FAIL 0 and PASS 0 (nothing executed). NO TEST 4 (QA-044, 049, 050, 051). PARTIAL 8
(QA-009, 016, 017, 020, 040, 041, 045 and the weak QA-046/047 mappings noted). The rest are
UNIT-UNRUN or INT-UNRUN.
