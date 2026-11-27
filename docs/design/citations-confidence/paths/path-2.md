# Path 2: Persisted entity plus service

Core idea: `Citation` becomes a SQLAlchemy table in `src/data/models.py` with an Alembic migration. A `CitationService` scores hits, applies `min_confidence` and saves the citations of an answer through `PostgreSQLStore`. This is the literal reading of ADR-0008 and of the issue file list.

## Components
- Table `citation`: `id`, `answer_id` (plain string, no answer table exists), `tenant_id`, `law`, `article`, `paragraph`, `quote`, `confidence` (CHECK 0 to 1), `source_url`, `created_at`. Index on `(tenant_id, answer_id)`. RLS policy on `tenant_id` (assumption, not verified).
- `NOT_LEGAL_ADVICE_NOTICE` in `src/core/notices.py`.
- `RawHit`, `AnswerResult`, and `CitationService(store, min_confidence)` with `score`, `decide`, `save`.

## Scoring rule
- Confidence is the rerank score when present, else the retrieval score. No blending in v1.
- Same validation and boundary rule as path 1.

## Fit and risk
- Breaks three requirements: no database call in the module, no table or migration, no storing of citations.
- Needs an answer identity, an RLS design, DB integration tests and a rewrite of the ADR text. Effort L.
- Risk: the schema is fixed before the scoring weights and issue 96 exist. Quotes stored per tenant add a retention surface.
