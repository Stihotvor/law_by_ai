# QA results: worker DB pool size

Working directory: /home/yevhend/claude-projects/law_by_ai
Files (relative to it): S = tests/unit/config/test_settings_pool.py, P = tests/unit/plugins/test_postgres_pool.py, F = tests/unit/tasks/test_fetch_store.py, Q = tests/unit/test_qa_worker_db_pool_size.py (new), I = tests/integration/test_fetch_worker_pool.py, C = docker/docker-compose.yml.
Run: `.venv/bin/pytest -q -m "not integration"` on S, P, F, Q and tests/unit/tasks/test_fetch_close_store.py: 64 passed.

QA-001 pass: S::test_each_default, P::test_default_app_pool - default 5
QA-002 pass: S::test_each_default, P::test_default_app_pool - default 10
QA-003 pass: S::test_defaults - worker size 1
QA-004 pass: S::test_defaults - worker overflow 1
QA-005 pass: S::test_each_override, S::test_valid_override (override value differs from the case: same parse path)
QA-006 pass: S::test_each_override, S::test_valid_override (override value differs from the case: same parse path)
QA-007 pass: S::test_each_override, S::test_valid_override
QA-008 pass: S::test_each_override - "0" accepted
QA-009 pass: S::test_rejected_value
QA-010 pass: S::test_rejected_value
QA-011 pass: S::test_each_rejects (value "-5","1.5","x" for worker size; "0" not run for worker size, covered by PoolConfig/_int_at_least min 1 via POSTGRES_POOL_SIZE "0")
QA-012 pass: S::test_rejected_value
QA-013 pass: S::test_each_rejects ("-5")
QA-014 pass: S::test_each_rejects ("x"), S::test_rejected_value ("abc")
QA-015 pass: S::test_each_rejects ("1.5")
QA-016 pass: S::test_empty_value_uses_default
QA-017 pass: Q::test_empty_worker_values_use_defaults
QA-018 pass: Q::test_minimum_app_pool_is_accepted
QA-019 pass: S::test_pool_config_validates_itself
QA-020 pass: S::test_pool_config_validates_itself
QA-021 pass: Q::test_pool_config_is_frozen
QA-022 pass: P::test_default_app_pool
QA-023 pass: P::test_worker_pool (explicit 1+1; the "POSTGRES_POOL_SIZE=7" precondition is not set in that test, weak but code path takes pool arg)
QA-024 pass: Q::test_worker_settings_do_not_change_app_pool
QA-025 pass: Q::test_app_settings_do_not_change_worker_pool
QA-026 pass: P::test_bad_app_setting - ValueError, create_engine never called
QA-027 pass: S::test_rejected_value, S::test_each_rejects
QA-028 pass: P::test_engine_options - pool_pre_ping True (also with PoolConfig(1,1))
QA-029 pass: P::test_engine_options - pool_timeout 30
QA-030 not-automated: needs a real Postgres restart (Docker); no test written
QA-031 not-automated: needs a 30 s real wait on a live pool and a long-running test; no test written
QA-032 not-automated: needs the pool-timeout scenario plus UI re-run; no test written
QA-033 pass: F::test_bad_worker_value_raises_and_leaves_store_none (uses "0", not "abc"; same ValueError path, named variable)
QA-034 pass: F::test_bad_worker_value_raises_and_leaves_store_none ("0"), S::test_rejected_value (-1)
QA-035 pass: F::test_retry_after_bad_value
QA-036 pass: Q::test_repeated_requests_reuse_one_store
QA-037 pass: F::test_task_gets_store_from_make_store, F::test_only_make_store_builds_the_store
QA-038 pass (Docker suite 2026-11-16: 1393 passed): I::test_fetch_document_worker_pool
QA-039 not-automated: worker --concurrency=2 with 10 queued tasks and live pg_stat_activity count; manual/Docker
QA-040 pass: Q::test_compose_passes_app_pool_variables (static YAML check of C)
QA-041 pass: Q::test_compose_passes_worker_pool_variables (static YAML check of C)
QA-042 not-automated: needs the stack started in Docker (static part: bare keys in C checked by QA-040/041)
QA-043 pass: Q::test_env_example_lists_pool_variables
QA-044 pass: Q::test_settings_docs_table_lists_pool_defaults
QA-045 partial: Q::test_compose_init_gets_no_pool_variables checks init gets none (code default 5+10 applies); the run-and-exit part needs Docker
QA-046 not-automated: gate (lint, type check, fast tests, diff-cover 90%) not run here; main session runs it

Counts: pass 39 (QA-038 verified in the Docker suite), partial 1 (QA-045), fail 0, not-automated 6 (QA-030, 031, 032, 039, 042, 046).
