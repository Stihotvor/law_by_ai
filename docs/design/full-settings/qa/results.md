# QA results: full settings

Working directory: /home/yevhend/claude-projects/law_by_ai
Files (relative to it): S = tests/unit/config/test_settings.py, D = tests/unit/config/test_settings_drift.py.
Run: `.venv/bin/pytest tests/unit/config -q`: 167 passed.

QA-001 pass: S::test_new_key_uses_default_when_unset[QDRANT_URL]
QA-002 pass: S::test_new_key_uses_default_when_unset[QDRANT_API_KEY]
QA-003 pass: S::test_new_key_uses_default_when_unset[QDRANT_COLLECTION]
QA-004 pass: S::test_new_key_uses_default_when_unset[OTEL_EXPORTER_OTLP_ENDPOINT]
QA-005 pass: S::test_new_key_uses_default_when_unset[OTEL_SERVICE_NAME]
QA-006 pass: S::test_new_key_uses_default_when_unset[MIN_CONFIDENCE]
QA-007 pass: S::test_new_key_uses_default_when_unset[RERANK_MODEL_NAME]
QA-008 pass: S::test_new_key_uses_default_when_unset[RERANK_MODEL_PATH]
QA-009 pass: S::test_new_key_takes_environment_value[QDRANT_URL] (value `qdrant:6333`, not `http://qdrant:6333`; same path)
QA-010 pass: S::test_new_key_takes_environment_value[QDRANT_API_KEY]
QA-011 pass: S::test_new_key_takes_environment_value[QDRANT_COLLECTION]
QA-012 pass: S::test_new_key_takes_environment_value[OTEL_EXPORTER_OTLP_ENDPOINT]
QA-013 pass: S::test_new_key_takes_environment_value[OTEL_SERVICE_NAME]
QA-014 pass: S::test_new_key_takes_environment_value[MIN_CONFIDENCE]
QA-015 pass: S::test_new_key_takes_environment_value[RERANK_MODEL_NAME]
QA-016 pass: S::test_new_key_takes_environment_value[RERANK_MODEL_PATH]
QA-017 pass: S::test_new_key_empty_value_uses_default[QDRANT_COLLECTION]
QA-018 pass: S::test_min_confidence_empty_uses_default
QA-019 pass: S::test_min_confidence_rejects_bad_value[abc]
QA-020 pass: S::test_min_confidence_rejects_bad_value[-0.1]
QA-021 pass: S::test_min_confidence_rejects_bad_value[1.1]
QA-022 pass: S::test_min_confidence_rejects_bad_value[nan]
QA-023 pass: S::test_min_confidence_rejects_bad_value[inf]
QA-024 pass: S::test_min_confidence_rejects_bad_value[   ]
QA-025 pass: S::test_min_confidence_accepts_valid_value[0-0.0]
QA-026 pass: S::test_min_confidence_accepts_valid_value[1-1.0]
QA-027 pass: S::test_min_confidence_accepts_valid_value[ 0.5 -0.5]
QA-028 pass: S::test_qa_028_bad_min_confidence_never_falls_back (new)
QA-029 pass: S::test_qa_029_value_change_read_on_next_access (new)
QA-030 pass: S::test_new_key_takes_environment_value[QDRANT_URL] (value `qdrant:6333`, no error)
QA-031 pass: S::test_qa_031_empty_rerank_values_do_not_fail (new)
QA-032 partial: S::test_new_key_uses_default_when_unset[OTEL_EXPORTER_OTLP_ENDPOINT] checks the empty value; the exporter switch is in the observability issue (case marks it OPEN)
QA-033 pass: S::test_qa_033_bad_min_confidence_error_has_no_api_key (new)
QA-034 pass: S::test_qa_034_qdrant_api_key_never_raises (new)
QA-035 pass: S::test_cohere_settings_are_gone (4 params)
QA-036 pass: S::test_old_rerank_keys_do_no_harm (no error), S::test_qa_036_old_rerank_keys_leave_defaults (new, defaults)
QA-037 pass: D::test_qa_037_config_source_has_no_cohere_text (new; text files under src/config)
QA-038 pass: D::test_env_example_has_no_cohere_key
QA-039 pass: D::test_qa_039_env_example_has_no_old_rerank_model_key (new)
QA-040 pass: D::test_compose_keeps_only_two_rerank_keys
QA-041 pass: D::test_qa_041_env_example_defaults_match_settings (new)
QA-042 pass: D::test_qa_042_env_example_explains_empty_otel_endpoint (new)
QA-043 pass: D::test_new_key_appears_in_all_three_places[QDRANT_URL]
QA-044 pass: D::test_new_key_appears_in_all_three_places[QDRANT_API_KEY]
QA-045 pass: D::test_new_key_appears_in_all_three_places[QDRANT_COLLECTION]
QA-046 pass: D::test_new_key_appears_in_all_three_places[OTEL_EXPORTER_OTLP_ENDPOINT]
QA-047 pass: D::test_new_key_appears_in_all_three_places[OTEL_SERVICE_NAME]
QA-048 pass: D::test_new_key_appears_in_all_three_places[MIN_CONFIDENCE]
QA-049 pass: D::test_new_key_appears_in_all_three_places[RERANK_MODEL_NAME]
QA-050 pass: D::test_new_key_appears_in_all_three_places[RERANK_MODEL_PATH]
QA-051 partial: D::test_qa_051_drift_check_catches_missing_key (new) checks the drift regex finds no `MIN_CONFIDENCE` line in a copy without it; it does not run the drift test itself against the copy
QA-052 pass: D::test_qa_052_docstring_lists_migration_lock_key (new)
QA-053 pass: S::test_qa_053_developer_env_cannot_change_defaults (new), S::test_env_keys_cover_new_keys, S::test_clear_env_removes_new_keys
QA-054 pass: existing LLM and embedding tests in S (test_llm_model_*) pass unchanged
QA-055 pass: main session gate run, `ruff check .` reports all checks passed
QA-056 pass: main session gate run, `ruff format --check .` reports 446 files already formatted
QA-057 pass: main session gate run, `pyright` reports 0 errors and 0 warnings
QA-058 pass: main session gate run, `pytest -m "not integration"` reports 1702 passed
QA-059 pass: main session gate run, diff-cover against `origin/main` reports 100% on changed lines

Counts: pass 57, partial 2 (QA-032, QA-051), fail 0, not-automated 0.
