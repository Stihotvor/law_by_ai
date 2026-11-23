# Path 1: keep the plain class

## Structure
`Settings` stays a plain class. Each new key is one `@property` over `os.getenv`, in the current style. Delete `rerank_base_url`, `rerank_api_key` and `rerank_model`. Add three sections: Qdrant, Observability, Rerank (local).

## New properties
- `qdrant_url`: `QDRANT_URL`, default `http://localhost:6333`. The property does not validate the URL.
- `qdrant_api_key`: `QDRANT_API_KEY`, default empty.
- `qdrant_collection`: `QDRANT_COLLECTION`, default `legal_documents`.
- `otel_exporter_otlp_endpoint`: `OTEL_EXPORTER_OTLP_ENDPOINT`, default empty. Empty means export off.
- `otel_service_name`: `OTEL_SERVICE_NAME`, default `law-by-ai`.
- `min_confidence`: `_float_in_range("MIN_CONFIDENCE", 0.5, 0.0, 1.0)`.
- `rerank_model_name` and `rerank_model_path`: default empty. An empty value does not fail.

## New helper
`_float_in_range(name: str, default: float, minimum: float, maximum: float) -> float`
- An empty or unset variable gives `default`.
- A value that is not a number raises `ValueError` that names the variable.
- A value outside `[minimum, maximum]` raises `ValueError`. The check `not (minimum <= value <= maximum)` also rejects `nan` and `inf`. The values 0 and 1 stay valid.
- The error message shows the raw value. This is acceptable because `MIN_CONFIDENCE` is not a secret. Only non-secret keys use the helper.

## Files touched
- `src/config/settings.py`: the properties, the helper and the docstring table (remove 3 rows, add 8).
- `docker/.env.example`: remove the 3 Cohere keys, add the 8 new keys.
- `docker/docker-compose.yml` `x-app-env`: remove the 3 old `RERANK_*` keys, add the 8 new keys.
- `tests/unit/config/test_settings.py`: default and override cases for each new key, plus the rejection cases `abc`, `-0.1`, `1.1`, `nan` and the boundary values 0 and 1.

## Failure modes
- A bad `MIN_CONFIDENCE` raises `ValueError` at the first read. Reads are lazy, the same as `_positive`.
- An old `.env` with `RERANK_BASE_URL` does no harm, because no code reads it.
- An empty OTLP endpoint returns `""`. The consumer treats it as export off.
- There is no fail-fast check at startup. This matches the current behavior.

## Effort
S. About 8 properties, one helper of about 12 lines, 3 deletions and the config files.

## Main risk
The docstring table, `.env.example` and the compose block can drift apart, because no single source of truth exists. The success-metric greps check only the removal.
