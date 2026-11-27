# Review: llm-client

Verdict: PASS WITH WARNINGS (2026-11-23, range origin/main..feature/llm-client). Final architect review: CLEAR.

## Gate
ruff check, ruff format --check, pyright (0 errors), bandit, pytest -m "not integration" (1830 passed), total coverage 98.88 %, diff coverage 100 %. TDD order: pass. `uv lock --check` failed only in the sandbox cache (`pyproject.toml` and `uv.lock` unchanged). pip-audit, mutation testing and the Docker integration suite run in CI (a local hook blocks the Docker env file).

## Fixed in review
- The `AgentLLMConfig` repr hides the key and the base URL.
- `httpx.InvalidURL` is wrapped into a secret-free `LLMError`. The base URL check rejects a missing host or a bad port.
- `Accept-Encoding: identity` is sent, so the 1 MiB cap counts wire bytes.
- Timeout errors name the variable but not the value. One shared validator, `positive_float`. `Settings.llm_var_name` and `Settings.llm_agent_timeout` own the env naming, and `core.llm` reads no env.
- After CodeRabbit: a compressed response is rejected before it is read, deeply nested JSON is a malformed response, a base URL with `?` or `#` is rejected, and a key needs https for a non-loopback host.
- After the final architect review: `LLM_BASE_URL` defaults to `http://localhost:11434/v1`, and a key with a non-ASCII or non-printable character is a config error.
- Named `_HTTPX_PHASES`, a flat `_parse_content`, `__all__`, and behavior names for tests.
- Timeout bound: each httpx phase gets timeout / 4 (owner decision after G1).

## Warnings kept
- Closed (2026-11-27, owner decision): medium, perf: a new `httpx.Client` for each call. `LLMClient` now makes one client on first use and reuses it. `close()` and the context manager free it, and the next call opens a new one.
- low, security: `http://` is allowed without a key for any host. A key needs https unless the host is loopback. There is no host allowlist. URLs come only from the environment.
- low, security: `trust_env=False` ignores custom CA bundles. Add an explicit setting when a private CA is needed.
- Closed (2026-11-27, owner decision): medium, availability (CodeRabbit): header trickle past the deadline. The real transport now uses an httpcore network backend that clips each connect, TLS handshake, read and write to the time left before the call deadline, so a trickle ends at about 1 x timeout. No thread and no new dependency. A custom `transport` gets no such clip and must enforce its own deadline: a header trickle can hold it with no upper bound. Writes go in 4 KiB slices, and each slice gets the time left. The fix sets the private `HTTPTransport._pool`, because httpx takes no network backend argument: check it on each httpx upgrade.
- low, structure: the module-level clock `_now` is patched in tests instead of being injected.
- low, structure: `settings.py` and `test_settings.py` were over 500 lines before this change.
- QA-046 partial: memory growth is not measured. The thread count is checked.
- Closed (2026-11-27, docs PR review): a raised error kept the `chat` frame, whose locals held the key, the base URL and the messages. `chat` now drops the traceback of the inner frames and deletes its arguments before the raise. A test walks `tb_frame.f_locals` over the whole traceback.
