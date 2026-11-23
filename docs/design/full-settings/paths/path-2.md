# Path 2: declarative pydantic-settings model

## Structure
- Rewrite `Settings` as a `pydantic_settings.BaseSettings` with typed fields and no env prefix. The about 70 current keys become fields with their current defaults.
- `min_confidence` is a `float` field with a `field_validator`. The validator rejects non-numbers, values below 0, values above 1 and `nan`. The error names the variable and does not show the value.
- Secrets such as `QDRANT_API_KEY` become `SecretStr`.
- Derived values (`postgres_url`, `redis_url`, `celery_*`, the pool config) stay as properties.
- The model config sets `extra="ignore"`, `env_ignore_empty=True` and `hide_input_in_errors=True`.
- Remove the 3 Cohere keys and add the 8 new keys.

## Lazy reads and current tests
- Today each property reads `os.getenv` at each access. A `BaseSettings` reads the environment once, at construction. This breaks the lazy-read contract.
- The tests that call `monkeypatch.setenv` after construction must clear `get_settings` or build a new `Settings()`. There are 6 test files in `tests/unit/config/`.
- A bad `MIN_CONFIDENCE` then fails at construction, so it breaks startup for every caller, also for callers that never read it. This differs from the requirement "fails at first read".

## Files touched
- `pyproject.toml` and the lockfile: add `pydantic-settings` (new dependency).
- `src/config/settings.py`: a full rewrite. `Field` constraints replace `_positive` and `_int_at_least`.
- `docker/.env.example` and `docker/docker-compose.yml`: the same key changes as Path 1.
- All 6 test files in `tests/unit/config/`, plus the new cases.
- Possibly call sites that use `Settings()` directly.

## Failure modes
- A bad `MIN_CONFIDENCE` raises `ValidationError`, which is a subclass of `ValueError`.
- An old `RERANK_BASE_URL` does no harm, because of `extra="ignore"`.
- By default, a pydantic error message shows the input value. `hide_input_in_errors=True` is necessary to keep secrets out of error messages.

## Effort
L. A rewrite of 602 lines, a new dependency and a change to the test contract in 6 files.

## Main risk
The read-once behavior changes the contract that all current tests rely on. Other risks: an error message that shows a secret if the config is wrong, and a Docker image rebuild for the new dependency.
