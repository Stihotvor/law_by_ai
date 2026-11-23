# Review: llm-client

Verdict: PASS WITH WARNINGS (2026-11-23, range origin/main..feature/llm-client).

## Gate
ruff check, ruff format --check, pyright (0 errors), bandit, pytest -m "not integration" (1800 passed), total coverage 98.84 %, diff coverage 100 %. TDD order: pass. `uv lock --check` failed only in the sandbox cache (`pyproject.toml` and `uv.lock` unchanged). pip-audit, mutation testing and the Docker integration suite run in CI (a local hook blocks the Docker env file).

## Fixed in review
- The `AgentLLMConfig` repr hides the key and the base URL.
- `httpx.InvalidURL` is wrapped into a secret-free `LLMError`. The base URL check rejects a missing host or a bad port.
- `Accept-Encoding: identity` is sent, so the 1 MiB cap counts wire bytes.
- Timeout errors name the variable but not the value. One shared validator, `positive_float`. `Settings.llm_var_name` and `Settings.llm_agent_timeout` own the env naming, and `core.llm` reads no env.
- Named `_HTTPX_PHASES`, a flat `_parse_content`, `__all__`, and behavior names for tests.
- Timeout bound: each httpx phase gets timeout / 4 (owner decision after G1).

## Warnings kept
- medium, perf: a new `httpx.Client` for each call. Kept to match the Mistral adapter and to keep the client stateless. Revisit when an agent makes many calls in a loop.
- low, security: `http://` is allowed for any host, and there is no host allowlist. URLs come only from the environment.
- low, security: `trust_env=False` ignores custom CA bundles. Add an explicit setting when a private CA is needed.
- low, security: a server that ignores `identity` and sends gzip is still decoded before the cap.
- low, structure: the module-level clock `_now` is patched in tests instead of being injected.
- low, structure: `settings.py` and `test_settings.py` were over 500 lines before this change.
- QA-046 partial: memory growth is not measured. The thread count is checked.
