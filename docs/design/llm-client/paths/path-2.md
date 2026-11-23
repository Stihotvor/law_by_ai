# Path 2: Hexagonal port, open convention

Core idea: agents depend on a `ChatModel` Protocol. An `OpenAICompatibleClient` adapter implements it. A convention resolver builds env names from the agent name (`LLM_<FIELD>_<AGENT>`, then `LLM_<FIELD>`).

## Components
- `src/core/llm/ports.py`: `ChatModel` Protocol, `chat(agent_name, messages) -> str`.
- `errors.py`: `LLMError(msg, status_code=None)`, `LLMConfigError(LLMError)`, `LLMTimeoutError(LLMError)`.
- `config.py`: `AgentLLMConfig` frozen dataclass and `resolve(settings, agent_name)`.
- `client.py`: `OpenAICompatibleClient(settings, *, transport=None)`, alias `LLMClient`.
- `settings.py`: generic `llm_setting(field, agent)`, `llm_timeout`, `known_llm_agents()` derived from `llm_model_*` property names. Existing properties untouched.

## Flow and errors
- Empty `messages`: `ValueError`. Unknown agent (not in allow-list) or empty model: `LLMConfigError`, no request.
- `httpx.TimeoutException` -> `LLMTimeoutError`, plus a monotonic deadline across the read.
- Other `httpx.HTTPError` -> `LLMError(status_code=None)`. Non-2xx (redirects too) -> `LLMError(status_code=n)`. Bad 200 body -> `LLMError(status_code=200)`.
- No key or content in error text, no logging, `trust_env=False`, `follow_redirects=False`.

## Files
New `src/core/llm/{__init__,ports,errors,config,client}.py` and tests. Edited `src/config/settings.py` (about 40 lines), `.env.example`.

## Effort and risks
Effort S-M.
1. Generic env lookup: an env-name typo falls back to the global value silently.
2. Allow-list from property-name introspection is brittle on rename.
3. The port has one implementation, so it is ceremony until a second backend exists. It does let agents test against a fake `ChatModel`.

Choose it when agents are added often and agent tests need a fake model.
