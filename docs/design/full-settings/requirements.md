# Requirements: full settings

## Business Goals
- Later features (Qdrant search, local rerank, confidence filter, observability) read their configuration from one place: `Settings` in `src/config/settings.py`.
- The Cohere keys go away, because the charter replaced Cohere with a local rerank model. An operator who reads `docker/.env.example` must not see a Cohere key.
- Why now: seven issues depend on these keys (search service, rerank, observability, confidence filter).
- Decided: add the keys now, so that dependent issues do not each edit the settings file.

## Technical Constraints
- Python 3.13. `Settings` is a plain class. Each value is a property that reads `os.getenv`. Validation helpers exist (`_positive`).
- Remove `RERANK_BASE_URL`, `RERANK_API_KEY`, `RERANK_MODEL` from `settings.py`, `docker/.env.example` and the `x-app-env` block of `docker/docker-compose.yml`.
- Add these keys with defaults:
  - `QDRANT_URL` = `http://localhost:6333`
  - `QDRANT_API_KEY` = empty
  - `QDRANT_COLLECTION` = `legal_documents`
  - `OTEL_EXPORTER_OTLP_ENDPOINT` = empty (empty means export off, owner decision)
  - `OTEL_SERVICE_NAME` = `law-by-ai`
  - `MIN_CONFIDENCE` = `0.5`
  - `RERANK_MODEL_NAME` = empty
  - `RERANK_MODEL_PATH` = empty
- No `rerank_enabled` setting (owner decision in the issue).
- Keep the LLM and embedding keys unchanged.
- `src/config/.env.example` does not exist. Update only `docker/.env.example`. The PR says so.
- Out of scope: the failed-task registry settings (owner decision: the registry issue adds them), the plugin-era Cohere leftovers outside `src/config` (`RerankingPlugin`), the choice of a rerank model.
- Decided at G1: keep the plain class (Path 1). No pydantic-settings rewrite.

## Edge Cases
- `MIN_CONFIDENCE` that is not a number (for example `abc`) raises `ValueError` that names the variable.
- `MIN_CONFIDENCE` lower than 0 or higher than 1 raises `ValueError`. The values 0 and 1 are valid.
- An empty or unset variable uses its default.
- A whitespace-only `MIN_CONFIDENCE` (`"   "`) raises `ValueError`, the same as `_int_at_least` does for an integer key.
- `RERANK_MODEL_NAME` and `RERANK_MODEL_PATH` are empty by default. Settings do not fail on empty values. The search service fails hard when it needs the model and the value is empty (that check belongs to the search issue).
- `QDRANT_URL` with no scheme is accepted as a string. URL validation is the client's task.

## Failure Modes
- A bad `MIN_CONFIDENCE` value fails at first read with a `ValueError`. It never falls back silently to the default.
- An old `.env` file that still sets `RERANK_BASE_URL` does no harm: no code reads it.
- An empty `OTEL_EXPORTER_OTLP_ENDPOINT` means no export. The app starts with no collector. The app observability code owns this switch: it configures an exporter only when the setting is not empty. It does not rely on the OTel SDK default (`localhost:4317`).
- No secret value appears in a log or an error message. Error messages name the variable, not the value, for `QDRANT_API_KEY`.

## Success Metrics
- `grep -riE 'cohere|rerank_base_url|rerank_api_key' src/config docker/.env.example` returns 0 lines.
- `RERANK_` keys in `docker/docker-compose.yml`: only `RERANK_MODEL_NAME` and `RERANK_MODEL_PATH` (2 lines).
- `Settings` has 0 attributes named `rerank_enabled`, `rerank_base_url`, `rerank_api_key` or `rerank_model`.
- A unit test checks that each of the 8 new keys appears in the `Settings` docstring table, in `docker/.env.example` and in the compose `x-app-env` block.
- Each of the 8 new keys has a default test and an override test: at least 16 unit cases.
- `MIN_CONFIDENCE` has at least 5 rejection cases: `abc`, `-0.1`, `1.1`, `nan`, `inf`. Surrounding whitespace (` 0.5 `) is accepted.
- Gate: ruff check, ruff format --check, pyright, fast tests, diff-cover 90% or more on changed lines. The CI mutation gate covers only `src/agents/fetch/`, so it does not apply to this change.
