# Decision: full settings

## Context
`Settings` (`src/config/settings.py`) is a plain class. Each value is a property that reads `os.getenv`. The issue removes the 3 Cohere rerank keys. It adds 8 keys for Qdrant, OTel, `min_confidence` and the local rerank model. The issue left one question OPEN: a pydantic-settings rewrite or the plain class.

## Options
The work is size S (one module, no data or interface change), so the design-divergence flow used 2 paths, not 4.
- Path 1: extend the plain class with 8 properties and one `_float_in_range` helper. Effort S. Reviewer: FEASIBLE WITH CHANGES.
- Path 2: rewrite the class as a pydantic-settings `BaseSettings`. Effort L, new dependency, reads once at construction. Reviewer: FEASIBLE WITH CHANGES at high cost.

## Decision
Path 1, chosen by the owner at G1. The reasons:
- It keeps the requirement that a bad value fails at the first read, not at startup.
- It adds no dependency, and the current tests keep the lazy-read contract.
- It keeps the scope to the issue.

Reviewer changes taken into the design:
- `MIN_CONFIDENCE` rejects `inf` too (5 rejection cases).
- Add the 8 new keys to `_ENV_KEYS` in `tests/unit/config/test_settings.py`, so a developer `.env` cannot change the default tests.
- Rename the section header "LLM / embeddings / reranking" and update the docstring table. Add the missing `MIGRATION_LOCK_TIMEOUT_S` row.
- Add all 8 new keys to the `x-app-env` block of `docker/docker-compose.yml`.
- A whitespace-only `MIN_CONFIDENCE` raises `ValueError`.
- A unit test checks that the 8 new keys appear in the docstring table, `docker/.env.example` and the compose block. This limits the drift risk for the new keys.

## Consequences
- The config is not typed or secret-safe the pydantic way. Secrets stay plain `str`.
- The docstring table, `docker/.env.example` and the compose block can still drift apart for the older keys. A test checks the new keys only.
- Owner decisions:
  - The failed-task registry settings are deferred to the registry issue.
  - An empty OTel endpoint means export off. The observability code owns the switch.
- The plugin-era Cohere leftovers (`plugins.yaml`, `RerankingPlugin`) stay. They are out of scope.
- `src/config/.env.example` does not exist. The PR says so.
