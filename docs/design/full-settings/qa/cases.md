# QA cases: full settings

### QA-001 QDRANT_URL default
- Covers: Technical Constraints QDRANT_URL default; T1 default scenario
- Type: functional
- Given QDRANT_URL is not set
- When the code reads the Qdrant URL on a new Settings
- Then the value is `http://localhost:6333`

### QA-002 QDRANT_API_KEY default
- Covers: Technical Constraints QDRANT_API_KEY default; T1 default scenario
- Type: functional
- Given QDRANT_API_KEY is not set
- When the code reads the Qdrant API key on a new Settings
- Then the value is an empty string

### QA-003 QDRANT_COLLECTION default
- Covers: Technical Constraints QDRANT_COLLECTION default; T1 default scenario
- Type: functional
- Given QDRANT_COLLECTION is not set
- When the code reads the Qdrant collection on a new Settings
- Then the value is `legal_documents`

### QA-004 OTLP endpoint default
- Covers: Technical Constraints OTEL_EXPORTER_OTLP_ENDPOINT default; Failure Mode empty endpoint means no export
- Type: functional
- Given OTEL_EXPORTER_OTLP_ENDPOINT is not set
- When the code reads the OTLP endpoint on a new Settings
- Then the value is an empty string

### QA-005 OTel service name default
- Covers: Technical Constraints OTEL_SERVICE_NAME default; T1 default scenario
- Type: functional
- Given OTEL_SERVICE_NAME is not set
- When the code reads the OTel service name on a new Settings
- Then the value is `law-by-ai`

### QA-006 MIN_CONFIDENCE default
- Covers: Technical Constraints MIN_CONFIDENCE default 0.5; T1 default scenario
- Type: functional
- Given MIN_CONFIDENCE is not set
- When the code reads the minimum confidence on a new Settings
- Then the value is 0.5

### QA-007 RERANK_MODEL_NAME default
- Covers: Technical Constraints RERANK_MODEL_NAME default; Edge Case empty rerank values
- Type: functional
- Given RERANK_MODEL_NAME is not set
- When the code reads the rerank model name on a new Settings
- Then the value is an empty string and no error is raised

### QA-008 RERANK_MODEL_PATH default
- Covers: Technical Constraints RERANK_MODEL_PATH default; Edge Case empty rerank values
- Type: functional
- Given RERANK_MODEL_PATH is not set
- When the code reads the rerank model path on a new Settings
- Then the value is an empty string and no error is raised

### QA-009 QDRANT_URL override
- Covers: Success Metric override test per key (QDRANT_URL)
- Type: functional
- Given QDRANT_URL is set to `http://qdrant:6333`
- When the code reads the Qdrant URL
- Then the value is `http://qdrant:6333`

### QA-010 QDRANT_API_KEY override
- Covers: Success Metric override test per key (QDRANT_API_KEY)
- Type: functional
- Given QDRANT_API_KEY is set to `k1`
- When the code reads the Qdrant API key
- Then the value is `k1`

### QA-011 QDRANT_COLLECTION override
- Covers: Success Metric override test per key (QDRANT_COLLECTION)
- Type: functional
- Given QDRANT_COLLECTION is set to `c1`
- When the code reads the Qdrant collection
- Then the value is `c1`

### QA-012 OTLP endpoint override
- Covers: Success Metric override test per key (OTEL_EXPORTER_OTLP_ENDPOINT)
- Type: functional
- Given OTEL_EXPORTER_OTLP_ENDPOINT is set to `http://alloy:4317`
- When the code reads the OTLP endpoint
- Then the value is `http://alloy:4317`

### QA-013 OTel service name override
- Covers: Success Metric override test per key (OTEL_SERVICE_NAME)
- Type: functional
- Given OTEL_SERVICE_NAME is set to `svc`
- When the code reads the OTel service name
- Then the value is `svc`

### QA-014 MIN_CONFIDENCE override
- Covers: Success Metric override test per key (MIN_CONFIDENCE)
- Type: functional
- Given MIN_CONFIDENCE is set to `0.8`
- When the code reads the minimum confidence
- Then the value is 0.8

### QA-015 RERANK_MODEL_NAME override
- Covers: Success Metric override test per key (RERANK_MODEL_NAME)
- Type: functional
- Given RERANK_MODEL_NAME is set to `bge-reranker`
- When the code reads the rerank model name
- Then the value is `bge-reranker`

### QA-016 RERANK_MODEL_PATH override
- Covers: Success Metric override test per key (RERANK_MODEL_PATH)
- Type: functional
- Given RERANK_MODEL_PATH is set to `/models/rerank`
- When the code reads the rerank model path
- Then the value is `/models/rerank`

### QA-017 Empty string key uses default
- Covers: Edge Case empty or unset variable uses default
- Type: edge
- Given QDRANT_COLLECTION is set to an empty string
- When the code reads the Qdrant collection
- Then the value is `legal_documents`

### QA-018 Empty MIN_CONFIDENCE uses default
- Covers: Edge Case empty or unset variable uses default
- Type: edge
- Given MIN_CONFIDENCE is set to an empty string
- When the code reads the minimum confidence
- Then the value is 0.5

### QA-019 MIN_CONFIDENCE rejects abc
- Covers: Edge Case non-number; Success Metric rejection case `abc`
- Type: failure
- Given MIN_CONFIDENCE is set to `abc`
- When the code reads the minimum confidence
- Then a ValueError is raised and its message contains `MIN_CONFIDENCE`

### QA-020 MIN_CONFIDENCE rejects -0.1
- Covers: Edge Case lower than 0; Success Metric rejection case `-0.1`
- Type: failure
- Given MIN_CONFIDENCE is set to `-0.1`
- When the code reads the minimum confidence
- Then a ValueError is raised and its message contains `MIN_CONFIDENCE`

### QA-021 MIN_CONFIDENCE rejects 1.1
- Covers: Edge Case higher than 1; Success Metric rejection case `1.1`
- Type: failure
- Given MIN_CONFIDENCE is set to `1.1`
- When the code reads the minimum confidence
- Then a ValueError is raised and its message contains `MIN_CONFIDENCE`

### QA-022 MIN_CONFIDENCE rejects nan
- Covers: Success Metric rejection case `nan`
- Type: failure
- Given MIN_CONFIDENCE is set to `nan`
- When the code reads the minimum confidence
- Then a ValueError is raised and its message contains `MIN_CONFIDENCE`

### QA-023 MIN_CONFIDENCE rejects inf
- Covers: Success Metric rejection case `inf`; decision reviewer change
- Type: failure
- Given MIN_CONFIDENCE is set to `inf`
- When the code reads the minimum confidence
- Then a ValueError is raised and its message contains `MIN_CONFIDENCE`

### QA-024 MIN_CONFIDENCE rejects whitespace only
- Covers: Edge Case whitespace-only MIN_CONFIDENCE
- Type: failure
- Given MIN_CONFIDENCE is set to three spaces
- When the code reads the minimum confidence
- Then a ValueError is raised and its message contains `MIN_CONFIDENCE`

### QA-025 MIN_CONFIDENCE accepts 0
- Covers: Edge Case values 0 and 1 are valid (lower bound)
- Type: edge
- Given MIN_CONFIDENCE is set to `0`
- When the code reads the minimum confidence
- Then the value is 0.0

### QA-026 MIN_CONFIDENCE accepts 1
- Covers: Edge Case values 0 and 1 are valid (upper bound)
- Type: edge
- Given MIN_CONFIDENCE is set to `1`
- When the code reads the minimum confidence
- Then the value is 1.0

### QA-027 MIN_CONFIDENCE accepts surrounding whitespace
- Covers: Success Metric surrounding whitespace accepted
- Type: edge
- Given MIN_CONFIDENCE is set to ` 0.5 ` (one space on each side)
- When the code reads the minimum confidence
- Then the value is 0.5

### QA-028 Bad MIN_CONFIDENCE never falls back silently
- Covers: Failure Mode bad value fails at first read, no silent default
- Type: failure
- Given MIN_CONFIDENCE is set to `2`
- When the code reads the minimum confidence twice in a row
- Then both reads raise ValueError and neither returns 0.5

### QA-029 Value change is read on next access
- Covers: Decision lazy-read contract
- Type: functional
- Given a Settings instance read once with MIN_CONFIDENCE `0.3`
- When MIN_CONFIDENCE changes to `0.9` and the code reads it again
- Then the value is 0.9

### QA-030 QDRANT_URL without scheme accepted
- Covers: Edge Case QDRANT_URL with no scheme
- Type: edge
- Given QDRANT_URL is set to `qdrant:6333`
- When the code reads the Qdrant URL
- Then the value is `qdrant:6333` and no error is raised

### QA-031 Empty rerank model values do not fail
- Covers: Edge Case empty RERANK_MODEL_NAME and RERANK_MODEL_PATH
- Type: edge
- Given RERANK_MODEL_NAME and RERANK_MODEL_PATH are both set to an empty string
- When the code reads both properties
- Then both values are empty strings and no error is raised

### QA-032 Empty OTLP endpoint with no collector
- Covers: Failure Mode empty OTLP endpoint means no export
- Type: failure
- Given OTEL_EXPORTER_OTLP_ENDPOINT is empty and no collector runs
- When the code reads the OTLP endpoint
- Then the value is an empty string, which the observability code reads as export off
- OPEN: the exporter switch lives in the observability issue, so only the empty setting value is observable here

### QA-033 Bad MIN_CONFIDENCE error does not leak the API key
- Covers: Failure Mode no secret value in an error message
- Type: security
- Given QDRANT_API_KEY is set to `s3cret-key-123` and MIN_CONFIDENCE is set to `abc`
- When the code reads the minimum confidence
- Then the ValueError message does not contain `s3cret-key-123`

### QA-034 QDRANT_API_KEY never raises
- Covers: Failure Mode no secret value in an error message; T1 no validation of the key
- Type: security
- Given QDRANT_API_KEY is set to `  odd value  ` (with surrounding spaces)
- When the code reads the Qdrant API key
- Then no error is raised

### QA-035 Removed rerank attributes are gone
- Covers: Success Metric Settings has 0 rerank_enabled, rerank_base_url, rerank_api_key, rerank_model
- Type: functional
- Given a new Settings instance
- When the code checks for the four attributes `rerank_enabled`, `rerank_base_url`, `rerank_api_key`, `rerank_model`
- Then 0 of the four exist

### QA-036 Old Cohere env keys do no harm
- Covers: Failure Mode old .env still sets RERANK_BASE_URL
- Type: failure
- Given RERANK_BASE_URL is `http://old`, RERANK_API_KEY is `oldkey` and RERANK_MODEL is `old-model`
- When the code reads all 8 new properties
- Then no error is raised and each value is its default

### QA-037 Config source has no Cohere text
- Covers: Success Metric grep on src/config returns 0
- Type: functional
- Given the config source folder after the change
- When a case-insensitive search runs for `cohere`, `rerank_base_url` and `rerank_api_key`
- Then it returns 0 lines

### QA-038 Env example has no Cohere text
- Covers: Business Goal no Cohere key in docker/.env.example; Success Metric grep returns 0
- Type: functional
- Given the file `docker/.env.example` after the change
- When a case-insensitive search runs for `cohere`, `rerank_base_url` and `rerank_api_key`
- Then it returns 0 lines

### QA-039 Env example lists the old RERANK_MODEL key no more
- Covers: Technical Constraints remove RERANK_MODEL from .env.example
- Type: failure
- Given the file `docker/.env.example` after the change
- When a search runs for a line that starts with `RERANK_MODEL=` (exact key, not `RERANK_MODEL_NAME=`)
- Then it returns 0 lines

### QA-040 Compose has exactly two RERANK lines
- Covers: Success Metric RERANK_ keys in compose: 2 lines
- Type: functional
- Given the file `docker/docker-compose.yml` after the change
- When the count of lines containing `RERANK_` runs
- Then the count is 2 and the lines are `RERANK_MODEL_NAME` and `RERANK_MODEL_PATH`

### QA-041 Env example defaults match settings
- Covers: T2 add 8 keys with defaults to .env.example
- Type: functional
- Given the file `docker/.env.example` after the change
- When the lines for the 8 keys are read
- Then `QDRANT_URL=http://localhost:6333`, `QDRANT_COLLECTION=legal_documents`, `OTEL_SERVICE_NAME=law-by-ai` and `MIN_CONFIDENCE=0.5` are present, and the other 4 keys are present with empty values

### QA-042 Env example explains empty OTel endpoint
- Covers: T2 state that empty OTel endpoint means export off
- Type: functional
- Given the file `docker/.env.example` after the change
- When an operator reads the comment next to `OTEL_EXPORTER_OTLP_ENDPOINT`
- Then the comment says an empty value means export off

### QA-043 Drift test QDRANT_URL
- Covers: Success Metric drift test, key QDRANT_URL
- Type: functional
- Given the key `QDRANT_URL`
- When the drift test checks the Settings docstring table, `docker/.env.example` and the compose `x-app-env` block
- Then the key is found in all 3

### QA-044 Drift test QDRANT_API_KEY
- Covers: Success Metric drift test, key QDRANT_API_KEY
- Type: functional
- Given the key `QDRANT_API_KEY`
- When the drift test checks the 3 places
- Then the key is found in all 3

### QA-045 Drift test QDRANT_COLLECTION
- Covers: Success Metric drift test, key QDRANT_COLLECTION
- Type: functional
- Given the key `QDRANT_COLLECTION`
- When the drift test checks the 3 places
- Then the key is found in all 3

### QA-046 Drift test OTEL_EXPORTER_OTLP_ENDPOINT
- Covers: Success Metric drift test, key OTEL_EXPORTER_OTLP_ENDPOINT
- Type: functional
- Given the key `OTEL_EXPORTER_OTLP_ENDPOINT`
- When the drift test checks the 3 places
- Then the key is found in all 3

### QA-047 Drift test OTEL_SERVICE_NAME
- Covers: Success Metric drift test, key OTEL_SERVICE_NAME
- Type: functional
- Given the key `OTEL_SERVICE_NAME`
- When the drift test checks the 3 places
- Then the key is found in all 3

### QA-048 Drift test MIN_CONFIDENCE
- Covers: Success Metric drift test, key MIN_CONFIDENCE
- Type: functional
- Given the key `MIN_CONFIDENCE`
- When the drift test checks the 3 places
- Then the key is found in all 3

### QA-049 Drift test RERANK_MODEL_NAME
- Covers: Success Metric drift test, key RERANK_MODEL_NAME
- Type: functional
- Given the key `RERANK_MODEL_NAME`
- When the drift test checks the 3 places
- Then the key is found in all 3

### QA-050 Drift test RERANK_MODEL_PATH
- Covers: Success Metric drift test, key RERANK_MODEL_PATH
- Type: functional
- Given the key `RERANK_MODEL_PATH`
- When the drift test checks the 3 places
- Then the key is found in all 3

### QA-051 Drift test catches a missing key
- Covers: Decision drift test limits drift risk
- Type: failure
- Given a copy of `docker/.env.example` with the `MIN_CONFIDENCE` line deleted
- When the drift test runs against that copy
- Then the test fails for the key `MIN_CONFIDENCE`

### QA-052 Docstring table lists the migration lock key
- Covers: Decision add missing MIGRATION_LOCK_TIMEOUT_S row
- Type: functional
- Given the Settings module docstring table
- When an operator reads the row for `MIGRATION_LOCK_TIMEOUT_S`
- Then the row exists with default `300`

### QA-053 Developer .env cannot change default tests
- Covers: Decision add 8 keys to the test key list; T1 isolation scenario
- Type: edge
- Given a developer environment that sets `MIN_CONFIDENCE=0.9` and `QDRANT_URL=http://dev:1`
- When the default tests run
- Then they read 0.5 and `http://localhost:6333`

### QA-054 Existing LLM and embedding keys unchanged
- Covers: Technical Constraints keep LLM and embedding keys unchanged
- Type: functional
- Given the existing LLM and embedding properties, each with its old test
- When the unit tests for them run
- Then all of them pass with no edit to their expected values

### QA-055 Lint check passes
- Covers: Success Metric gate, ruff check; T3
- Type: functional
- Given the branch with T1 and T2 applied
- When `ruff check` runs
- Then it exits 0

### QA-056 Format check passes
- Covers: Success Metric gate, ruff format --check; T3
- Type: functional
- Given the same branch
- When `ruff format --check` runs
- Then it exits 0

### QA-057 Type check passes
- Covers: Success Metric gate, pyright; T3
- Type: functional
- Given the same branch
- When pyright runs
- Then it exits 0

### QA-058 Fast tests pass
- Covers: Success Metric gate, fast tests; T3
- Type: functional
- Given the same branch
- When `pytest -m "not integration"` runs
- Then it exits 0 and at least 16 new key cases and 5 MIN_CONFIDENCE rejection cases ran

### QA-059 Changed-line coverage
- Covers: Success Metric gate, diff-cover 90%
- Type: performance
- Given the same branch and the coverage data of the fast tests
- When diff-cover compares with `main`
- Then the report shows 90% or more on changed lines
