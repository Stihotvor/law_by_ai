# Decision: llm-client

## Context
Agents need one client to call an OpenAI-compatible server, with a base URL, model, timeout and API key per agent. Settings already has `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` and seven `LLM_MODEL_<AGENT>` properties. It has no timeout and no per-agent URL or key. Requirements: `requirements.md`.

## Options
- Path 1: Settings resolves the full per-agent config over a closed tuple. `config` would import the error from `core` (feasible with changes).
- Path 2: a `ChatModel` port, an `LLMClient` adapter and a resolver in `src/core/llm/`. Settings gets only a generic lookup (feasible with changes, recommended by the architect).

## Decision
Path 2, with the review changes (owner choice at G1, 2026-11-23):
- `src/core/llm/config.py` holds an explicit `LLM_AGENTS` tuple of the seven names, `AgentLLMConfig` (frozen: `base_url`, `model`, `timeout`, `api_key`) and `resolve(settings, agent_name)`. A test checks the tuple against the seven `llm_model_*` properties.
- Settings adds `llm_setting(field, agent)`: `LLM_<FIELD>_<AGENT>`, then `LLM_<FIELD>`. It adds `llm_timeout` (`LLM_TIMEOUT`, default 60 s, positive float, else `ValueError` naming the variable). `resolve` raises `ValueError` that names `LLM_TIMEOUT_<AGENT>` for a bad per-agent value. Existing properties stay. Settings raises only `ValueError`.
- `src/core/llm/ports.py`: `ChatModel` Protocol, `chat(agent_name, messages) -> str`.
- `src/core/llm/errors.py`: `LLMError(message, status_code=None)` and `LLMTimeoutError(LLMError)`. `LLMConfigError` is separate (base `Exception`), so a caller that catches `LLMError` does not treat config as transport.
- `src/core/llm/client.py`: `LLMClient(settings, *, transport=None)`, the only public name. It follows the Mistral adapter (`follow_redirects=False`, `trust_env=False`, no logging), streams the body with a 1 MiB cap and a monotonic deadline checked before each read and after each chunk, and passes `httpx.Timeout(timeout / 4)` to the request. Worst case is about 1.25 × timeout. A single slow read gets at most timeout / 4. (Changed after G1 by the owner: httpx limits each phase separately, so a bound of timeout + 1 s is not possible without a thread.) Errors never hold the key, the content or the base URL. A base URL with credentials, a query, a fragment, or a scheme other than http/https raises `LLMConfigError` that names the agent, and no request is sent. `http://` stays allowed for local servers. A trailing `/` is stripped before the join.
- The issue Gherkin names change to `bureaucracy_assistant` and `document_processor`, and the issue gets a Contract section.

## Consequences
- Config stays a leaf module. Agent tests can use a fake `ChatModel`.
- A typo in a per-agent env name falls back to the global value without a warning. Accepted risk.
- A new agent needs one name in `LLM_AGENTS` and one `llm_model_*` property.
- Effort S-M: about 40 lines in Settings, four new small modules and their unit tests.
