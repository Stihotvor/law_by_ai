# Requirements: llm-client

Source: issue "OpenAI-compatible LLM client". Facts come from `src/config/settings.py`, `src/agents/fetch/ocr/mistral.py` and the httpx docs.

## Business Goals
- Each agent calls its own model on a local OpenAI-compatible server through one client. Today no client exists, so no agent can call a model.
- The client unblocks the agent work in milestone "Phase 5 - Agents".
- Decided: one shared client, `LLMClient.chat(agent_name, messages) -> str`, in `src/core/llm/client.py`.

## Technical Constraints
- Python 3.13, `httpx==0.28.1` (already a main dependency). No new dependency.
- Settings stay a plain class with lazy `os.getenv` properties. Invalid values raise `ValueError` that names the variable.
- Per agent: base URL, model, timeout, API key. Each falls back to a global value: `LLM_BASE_URL`, `LLM_MODEL`, `LLM_TIMEOUT`, `LLM_API_KEY`.
- The existing `LLM_MODEL_<AGENT>` variables and the seven agent names stay valid (document_fetcher, document_processor, legal_research, change_tracker, knowledge_graph, analysis, bureaucracy_assistant).
- Request: `POST {base_url}/chat/completions` with body `{"model", "messages"}`. Strip a trailing `/` from `base_url` before the join. Answer: `choices[0].message.content`.
- Follow the Mistral OCR adapter: `follow_redirects=False`, `trust_env=False`, injectable transport, no log line with the key or the message content.
- Budget: 4-6 GB RAM host. The client holds no model and adds no background thread.
- Non-goals: streaming, tool calls, model choice, retries.

## Edge Cases
- Unknown agent name: `chat` raises `LLMConfigError` that names the agent. No HTTP request is sent.
- Agent with no model (empty per-agent and global value): `LLMConfigError` that names the agent and the variable.
- Empty `messages` list: `ValueError` before any request.
- Response body larger than 1 MiB: `LLMError` (fixed cap, not configurable).
- Agent names are the seven code names. The issue Gherkin uses `bureaucracy_assistant` and `document_processor` (owner decision at G1, no alias).
- Base URL with credentials, a query, a fragment, or a scheme other than http/https: `LLMConfigError` that names the agent. No request is sent.
- API key set with a plain `http://` base URL to a non-loopback host: `LLMConfigError` that names the agent. No request is sent.
- API key with a non-ASCII or non-printable character: `LLMConfigError` that names the agent and does not hold the key.
- `LLM_BASE_URL` unset: the base URL is `http://localhost:11434/v1`.
- Empty API key: the client sends no `Authorization` header.
- Response with no `choices`, or a non-string content, or non-JSON body: `LLMError` (status 200 kept on the error).
- Timeout value not a positive number: `ValueError` from Settings or `resolve` that names the variable.

## Failure Modes
- Server slower than the timeout: `LLMTimeoutError` (subclass of `LLMError`) within 1.25 × timeout + 1 s. httpx limits each phase separately, so each phase (pool, connect, write, read) gets timeout / 4 and a monotonic deadline is checked between body chunks (owner decision after G1, 2026-11-23).
- HTTP status not 2xx: `LLMError` with `status_code`. The error text holds no API key, no message content and no base URL.
- Connection refused or other transport error: `LLMError` with `status_code=None`.
- The client never retries. The caller (a Celery task) decides what to do (ADR-0006 stores failed tasks).

## Success Metrics
- 5 of 5 Gherkin scenarios of the issue pass as unit tests with `httpx.MockTransport`.
- Timeout test: `chat` raises within 1.25 × timeout + 1 s (1.25 s for the 0.2 s test timeout). A stall after one chunk is covered.
- Line coverage of `src/core/llm/` is 100 % in unit tests. Diff coverage meets the CONTRIBUTING.md gate.
- Quality gate: ruff check, ruff format --check, pyright, pytest all pass with 0 errors.
- 0 occurrences of the API key value and the base URL in any raised error text (checked by a test).
