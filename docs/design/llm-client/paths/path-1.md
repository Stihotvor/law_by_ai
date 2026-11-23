# Path 1: Closed registry, settings-owned

Core idea: Settings owns all LLM config resolution over a fixed tuple of the seven agent names. `LLMClient` is a thin class that asks Settings for a frozen config and does the HTTP call.

## Components
- `LLM_AGENTS: tuple[str, ...]` in `settings.py` (closed registry).
- `LLMAgentConfig` frozen dataclass: `base_url, model, timeout, api_key`.
- `Settings.llm_agent_config(agent: str) -> LLMAgentConfig`.
- `Settings.llm_timeout` (`LLM_TIMEOUT`), positive float.
- `LLMClient(settings, transport: httpx.BaseTransport | None = None).chat(agent_name, messages) -> str`.
- `src/core/llm/errors.py`: `LLMError(msg, status_code=None)`, `LLMTimeoutError(LLMError)`, `LLMConfigError`.

## Interfaces
- Per field: `LLM_<FIELD>_<AGENT>`, then global `LLM_<FIELD>`. `LLM_MODEL_<AGENT>` already fits.
- The seven `llm_model_<agent>` properties become wrappers over `llm_agent_config(...).model`.
- Unknown agent or empty model: `LLMConfigError` naming the agent (and the variable).
- Bad timeout: `ValueError` naming the variable.
- Settings imports `LLMConfigError` from `core.llm` (config depends on core).

## Error mapping
| Case | Result |
|---|---|
| Unknown agent | `LLMConfigError`, no request |
| Empty `messages` | `ValueError`, no request |
| Empty API key | no `Authorization` header |
| `httpx.TimeoutException` | `LLMTimeoutError` |
| Other `httpx.HTTPError` | `LLMError(status_code=None)` |
| Non-2xx | `LLMError(status_code=n)`, no key or body in text |
| Bad 200 body | `LLMError(status_code=200)` |

Mistral pattern: `follow_redirects=False`, `trust_env=False`, injected transport, no logging, no retries, a monotonic deadline across the streamed read so the total stays within timeout + 1 s.

## Files
`src/config/settings.py`, new `src/core/llm/{__init__,client,errors}.py`, client and settings unit tests, `.env.example`.

## Effort and risks
Effort M (settings tests cover 7 agents x 4 fields).
1. A new agent needs a settings edit, and the registry can drift from the model properties.
2. `config` depends on `core` for the error type.
3. A typo in one of 28 per-agent variables falls back to the global value silently.

Choose it when the agent set is stable and validation should live in one place.
