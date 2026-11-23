# QA results: llm-client

Files: C = /home/yevhend/claude-projects/law_by_ai/tests/unit/core/llm/test_client.py, G = .../tests/unit/core/llm/test_config.py, S = .../tests/unit/config/test_settings.py, E = .../tests/unit/core/llm/test_errors.py

QA-001: pass — C::test_bureaucracy_assistant_gets_an_answer — model, answer, URL
QA-002: pass — C::test_document_processor_uses_its_own_model_and_key
QA-003: pass — C::test_global_model_is_fallback
QA-004: pass — C::test_agent_url_and_key_override_global — timeout override: G::test_per_agent_value_wins
QA-005: pass — C::test_bureaucracy_assistant_gets_an_answer — body keys exactly model and messages
QA-006: pass — C::test_bureaucracy_assistant_gets_an_answer — env base URL has trailing slash
QA-007: pass — C::test_empty_key_sends_no_authorization_header
QA-008: pass — C::test_unknown_agent_sends_no_request
QA-009: pass — C::test_old_agent_alias_is_rejected
QA-010: pass — C::test_no_model_sends_no_request
QA-011: pass — C::test_empty_messages_send_no_request
QA-012: pass — C::test_body_over_max_size_is_rejected
QA-013: pass — C::test_body_of_exactly_max_size_is_accepted
QA-014: pass — C::test_bad_base_url_sends_nothing
QA-015: pass — C::test_bad_base_url_sends_nothing
QA-016: pass — C::test_bad_base_url_sends_nothing
QA-017: pass — C::test_bad_base_url_sends_nothing — ftp and file
QA-018: pass — C::test_http_localhost_is_allowed
QA-019: pass — G::test_base_url_defaults_when_unset, S::test_llm_setting_base_url_defaults_when_unset — resolver level
QA-020: pass — C::test_http_and_transport_failures
QA-021: pass — C::test_http_and_transport_failures
QA-022: pass — C::test_http_and_transport_failures — int 5 used, not null
QA-023: pass — C::test_http_and_transport_failures
QA-024: pass — S::test_llm_timeout_rejects_bad_value
QA-025: pass — G::test_bad_per_agent_timeout — resolver level, value 0 and "soon" not -5
QA-026: pass — S::test_llm_timeout_defaults_to_60, S::test_llm_timeout_accepts_padded_number
QA-027: pass — C::test_slow_server_times_out
QA-028: pass — C::test_slow_server_times_out — slow body variant
QA-029: pass — E::test_error_hierarchy, C::test_slow_server_times_out
QA-030: pass — C::test_http_and_transport_failures — 500
QA-031: pass — C::test_error_status_is_not_retried
QA-032: pass — C::test_slow_server_times_out, test_body_over_one_mib, test_http_and_transport_failures (_assert_clean)
QA-033: pass — C::test_http_and_transport_failures — _refuse, status None
QA-034: pass — C::test_error_status_is_not_retried — 503
QA-035: pass — C::test_redirect_is_not_followed
QA-036: pass — C::test_proxy_env_is_ignored — MockTransport bypasses real proxying, so weak evidence; trust_env=False not asserted directly
QA-037: pass — C::test_key_and_content_are_not_logged
QA-038: pass — C::test_repeated_calls_get_separate_answers
QA-039: pass — C::test_non_ascii_messages_sent_unchanged
QA-040: pass — G::test_llm_agents_match_settings
QA-041: pass — C::test_every_agent_uses_its_own_model
QA-042: pass — S::test_llm_model_global_and_agent_properties_unchanged
QA-043: pass — S::test_llm_setting_empty_when_both_unset
QA-044: pass — G::test_fake_satisfies_port — runtime check plus pyright 0 errors on tests/unit/core/llm (main session)
QA-045: pass — S::test_bad_llm_timeout_raises_plain_value_error
QA-046: partial — C::test_no_thread_left_after_100_calls — thread check only, memory growth not measured
QA-047: pass — pytest --cov=src/core/llm: 100% line and branch (122 stmts, 0 miss)
QA-048: pass — gate run by main session: ruff check, ruff format --check, pyright 0 errors, pytest -m "not integration" 1747 passed, diff-cover 100 %
QA-049: pass — QA-001, 002, 008, 027, 030 tests all pass
QA-050: pass — C::test_http_and_transport_failures — body [1]
