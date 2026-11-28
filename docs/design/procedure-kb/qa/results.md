# QA results: procedure-kb

Nothing was run by the test-engineer (Bash was blocked by a hook). Status `pass` means a test covers the case; unit tests are unrun by me, DB tests are run by the main session. NEW = test written in this pass, must be run.

Paths: P = tests/unit/core/procedures/test_models_parse.py, S = tests/unit/core/procedures/test_procedure_service.py, U = tests/unit/test_seed_procedures.py, SC = tests/integration/test_procedure_schema.py, R = tests/integration/test_procedure_repository.py, D = tests/integration/test_seed_db.py. All under /home/yevhend/claude-projects/law_by_ai/.claude/worktrees/priceless-nobel-258b03/. Line numbers were not captured (no shell); find tests by name.

| Case | Status | Tests | Note |
|---|---|---|---|
| QA-001 | pass | P::test_incomplete_step_names_the_step[fields0]; S::test_bad_input_writes_nothing | unit |
| QA-002 | pass | P::test_incomplete_step_names_the_step[fields1] | unit |
| QA-003 | pass | P::test_future_or_invalid_date_is_rejected[not-a-date] | unit; 2026-13-45 is a not-a-date case |
| QA-004 | pass | P::test_future_or_invalid_date_is_rejected[2026-11-28]; S::test_future_date_uses_injected_clock | unit |
| QA-005 | pass | P::test_last_checked_today_is_accepted | unit; "revision 1" part is DB (R::test_first_save_is_revision_one) |
| QA-006 | pass | P::test_incomplete_step_names_the_step[fields2] | unit |
| QA-007 | pass | P::test_incomplete_step_names_the_step[fields3] | unit |
| QA-008 | pass | P::test_incomplete_step_names_the_step[fields4] | unit |
| QA-009 | pass | P::test_structure_errors_set_source[zero-steps] | unit |
| QA-010 | pass | P::test_bad_url_is_rejected[http://...] | unit |
| QA-011 | pass | P::test_bad_url_is_rejected[ftp://...] | unit |
| QA-012 | pass | P::test_bad_url_is_rejected[https://user:pw@...]; P::test_error_message_holds_no_content | unit |
| QA-013 | pass | NEW U::test_qa_013_malformed_seed_file_names_the_file; U::test_every_bad_file_is_named | unit |
| QA-014 | pass | NEW U::test_qa_014_unknown_key_in_seed_file_names_the_file | unit |
| QA-015 | pass | P::test_unknown_step_field_names_the_step | unit |
| QA-016 | pass | P::test_structure_errors_set_source[bad-slug] | unit |
| QA-017 | pass | P::test_structure_errors_set_source[duplicate-keys]; P::test_duplicate_keys_name_the_step | unit |
| QA-018 | pass | NEW P::test_qa_018_blank_title_is_rejected | unit |
| QA-019 | pass | P::test_step_with_invalid_key_is_named_by_index | unit |
| QA-020 | pass | P::test_structure_errors_set_source[empty] | unit |
| QA-021 | pass | R::test_failed_save_keeps_old_data | DB test, run by main session. Failure forced at DB level (CHECK), not by validation |
| QA-022 | pass | R::test_failed_save_keeps_old_data; R::test_revision_conflict_maps_to_store_error; S::test_store_error_propagates_with_cause | DB test, run by main session |
| QA-023 | pass | R::test_first_save_is_revision_one | DB test, run by main session. "creation time" not asserted |
| QA-024 | pass | R::test_changed_content_is_next_revision | DB test, run by main session |
| QA-025 | pass | R::test_identical_content_writes_nothing | DB test, run by main session |
| QA-026 | pass | R::test_identical_content_writes_nothing | DB test, run by main session (other actor used) |
| QA-027 | pass | R::test_identical_content_writes_nothing | DB test, run by main session (row incl. updated_at compared) |
| QA-028 | pass | NEW P::test_qa_028_key_order_and_comments_do_not_change_content | unit; must be run |
| QA-029 | pass | NEW R::test_qa_029_changed_date_adds_a_revision | DB test, run by main session |
| QA-030 | pass | S::test_non_admin_import_is_refused_before_save | unit; "0 rows" shown by repo fake having no saves |
| QA-031 | pass | S::test_no_principal_import_is_refused_before_save | unit |
| QA-032 | pass | NEW S::test_qa_032_non_admin_with_invalid_yaml_gets_the_refusal_first | unit; must be run |
| QA-033 | pass | S::test_non_admin_import_is_refused_before_save | unit; no save call means revision unchanged |
| QA-034 | pass | S::test_admin_import_saves_once_with_actor | unit |
| QA-035 | pass | SC::test_app_role_cannot_change_history[update_revision] | DB test, run by main session |
| QA-036 | pass | SC::test_app_role_cannot_change_history[delete_revision] | DB test, run by main session |
| QA-037 | pass | SC::test_app_role_cannot_change_history[truncate_revision] | DB test, run by main session |
| QA-038 | pass | SC::test_app_role_cannot_change_history[delete_procedure] | DB test, run by main session |
| QA-039 | pass | SC::test_app_role_can_do_its_writes | DB test, run by main session |
| QA-040 | pass | SC::test_app_role_can_do_its_writes | DB test, run by main session (deletes steps, inserts again; 1 step not 4) |
| QA-041 | pass | SC::test_revision_rows_block_procedure_delete | DB test, run by main session |
| QA-042 | pass | NEW SC::test_qa_042_deleting_a_procedure_cascades_steps | DB test, run by main session |
| QA-043 | pass | SC::test_check_constraints_reject_bad_rows[empty_actor] | DB test, run by main session |
| QA-044 | pass | SC::test_check_constraints_reject_bad_rows[array_content] | DB test, run by main session |
| QA-045 | pass | NEW SC::test_qa_045_duplicate_revision_number | DB test, run by main session |
| QA-046 | pass | SC::test_check_constraints_reject_bad_rows[slug] | DB test, run by main session |
| QA-047 | pass | SC::test_check_constraints_reject_bad_rows[rev0] | DB test, run by main session |
| QA-048 | pass | SC::test_check_constraints_reject_bad_rows[http_url] | DB test, run by main session |
| QA-049 | pass | SC::test_check_constraints_reject_bad_rows[empty_text]; NEW SC::test_qa_049_051_more_check_constraints | DB test, run by main session |
| QA-050 | pass | NEW SC::test_qa_050_duplicate_step_position_and_key | DB test, run by main session |
| QA-051 | pass | SC::test_check_constraints_reject_bad_rows[title]; NEW SC::test_qa_049_051_more_check_constraints | DB test, run by main session |
| QA-052 | pass | SC::test_migration_round_trip | DB test, run by main session |
| QA-053 | pass | SC::test_downgrade_guards_history | DB test, run by main session |
| QA-054 | not-automated | none | Needs a second session holding a lock for 30 s; too slow and fragile for the suite |
| QA-055 | pass | R::test_concurrent_saves_get_consecutive_revisions[new_slug] | DB test, run by main session |
| QA-056 | pass | R::test_concurrent_saves_get_consecutive_revisions[existing_slug] | DB test, run by main session |
| QA-057 | pass | NEW R::test_qa_057_concurrent_identical_content | DB test, run by main session |
| QA-058 | pass | R::test_reader_never_sees_mixed_state | DB test, run by main session (20 writes, reads until done) |
| QA-059 | pass | R::test_first_save_is_revision_one (get equals saved) | DB test, run by main session |
| QA-060 | pass | R::test_unknown_slug_is_none; S::test_unknown_or_malformed_slug_returns_none | |
| QA-061 | pass | NEW S::test_qa_061_062_063_malformed_slugs_return_none | unit; must be run; "3 procedures still exist" not checked (no SQL reaches the store) |
| QA-062 | pass | NEW S::test_qa_061_062_063_malformed_slugs_return_none | unit; must be run |
| QA-063 | pass | NEW S::test_qa_061_062_063_malformed_slugs_return_none | unit; must be run |
| QA-064 | pass | R::test_list_is_sorted_by_slug; S::test_list_is_sorted_by_slug | |
| QA-065 | pass | R::test_not_found_and_empty; S::test_list_is_empty_without_procedures | |
| QA-066 | pass | NEW R::test_qa_066_read_after_engine_disposed | DB test, run by main session |
| QA-067 | pass | P::test_models_are_frozen | unit |
| QA-068 | pass | NEW P::test_qa_068_stale_date_is_kept_unchanged | unit parse only; DB round trip of date covered by R::test_first_save_is_revision_one |
| QA-069 | pass | R::test_failed_save_keeps_old_data; S::test_store_error_propagates_with_cause | DB test (content + cause) run by main session. Case says "database down"; tested via constraint failure |
| QA-070 | pass | P::test_step_schema_is_pinned | unit |
| QA-071 | pass | NEW P::test_qa_071_missing_schema_version_is_rejected | unit; must be run |
| QA-072 | pass | P::test_structure_errors_set_source[other-schema-version]; NEW P::test_qa_072_schema_version_99_is_rejected | Decided: version 1 only |
| QA-073 | pass | U::test_exactly_three_seed_files; D::test_seed_twice | D is DB test, run by main session |
| QA-074 | pass | U::test_seed_content_is_complete[*] | unit |
| QA-075 | pass | D::test_seed_twice | DB test, run by main session |
| QA-076 | pass | D::test_seed_twice; U::test_seed_imports_every_file_as_system_seed | |
| QA-077 | pass | U::test_duplicate_slug_stops_before_any_write | unit |
| QA-078 | pass | U::test_bad_seed_file_writes_nothing; U::test_main_exits_non_zero_naming_the_file; D::test_bad_file_writes_nothing | Decided: nothing written. Step name not asserted in the seed error |
| QA-079 | pass | NEW D::test_qa_079_seed_edit_adds_a_revision | DB test, run by main session; assumes `last_checked: <value>` format in pesel.yaml |
| QA-080 | not-automated | none | No test for a stopped server or password-free error text; needs a real unreachable URL. Suggest a follow-up |
| QA-081 | pass | D::test_seed_twice | DB test; seed runs with POSTGRES_URL as lawbyai_app |
| QA-082 | partial | U::test_seed_content_is_complete[*] | Verify line checked; "no advice wording" is a human read of the text (owner review) |
| QA-083 | pass | R::test_reads_are_fast | DB test, run by main session |
| QA-084 | pass | R::test_reads_are_fast | DB test, run by main session (1 call each, not 20) |
| QA-085 | pass | NEW R::test_qa_085_unknown_slug_is_fast | DB test, run by main session |
| QA-086 | pass | U::test_run_order_doc_migrate_before_seed | unit |
| QA-087 | not-automated | none | Manual owner gate: a test cannot prove an approving owner review |
| QA-088 | partial | NEW P::test_qa_088_two_hundred_steps_parse_in_order | Parse of 200 steps only; no DB import of 200 steps. No step limit by decision |
| QA-089 | not-automated | none | Decided: no size limit in this task; the upload page owns it |

Files changed: P, S, U (unit); SC, R, D (integration). None were run or linted by me.


## Run by the main session (2026-11-27)
- Unit: `tests/unit/core/procedures` and `tests/unit/test_seed_procedures.py`: 75 passed, 100 % coverage of `src/core/procedures`.
- Database (disposable PostgreSQL 18.6, roles from `docker/initdb`, migrated to head): `test_procedure_schema.py`, `test_procedure_repository.py`, `test_seed_db.py`: 41 passed. The whole integration suite: 260 passed, 9 skipped (no Valkey, no live Sejm), 2 failed in `test_login_flow.py` (cookie fake in the login UI, no shared code with this change, to be confirmed on CI).
- Final counts: pass 83, partial 2 (QA-082, QA-088), not-automated 4 (QA-054, QA-080, QA-087, QA-089), fail 0. `pass` for a database case means the main session saw it pass.
- Follow-up candidate: QA-080 (seed against a stopped server shows no password).
