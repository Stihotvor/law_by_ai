# Decision: citations-confidence

## Context
Every answer needs source links and a confidence score. A low score gives "no reliable answer" and the closest sources (ADR-0008, ADR-0015). The bureaucracy agent (issue 111) and the citation UI (issue 121) consume the result. The search service (issue 96) is not built. Requirements: `requirements.md`.

## Options
- Path 1: pure core module with frozen value types and one pure function (feasible with changes, recommended by the architect and the DBA).
- Path 2: stored `Citation` table plus `CitationService` (not feasible for this task: it breaks three requirements and needs an answer table, RLS and a retention rule).

## Decision
Path 1, with the review changes (owner choice at G1, 2026-11-27):
- `src/core/notices.py`: `NOT_LEGAL_ADVICE_NOTICE`, non-empty, holds "not legal advice".
- `src/core/citations.py`, stdlib only:
  - `ScoredHit` (frozen): `source_url`, `quote`, `retrieval_score`, `rerank_score: float | None`, and optional `law`, `article`, `paragraph`, `document_id`.
  - `Citation` (frozen): the same fields with one `confidence`.
  - Result is a tagged union: `Answer(citations, confidence, notice)` or `NoReliableAnswer(closest_sources, notice)`. The refusal type has no citations and no confidence, so a caller cannot read an answer from a refusal. Callers branch with `match`.
  - `decide(hits, min_confidence) -> Answer | NoReliableAnswer`.
- Input contract: both scores are already in [0, 1]. The search adapter (issue 96) normalizes raw scores. A bool, NaN, infinity or out-of-range value raises `ValueError` that names the field. The bool check runs before the number check.
- Rule: no rerank score gives confidence = retrieval score. Both scores give `RETRIEVAL_WEIGHT * retrieval + RERANK_WEIGHT * rerank` with named constants 0.4 and 0.6. A test checks that they sum to 1.0. The weights are provisional until the evaluation runs.
- `Answer.citations` holds only valid hits with confidence `>= min_confidence`, sorted by confidence descending, stable on ties. `Answer.confidence` is the maximum. `NoReliableAnswer.closest_sources` holds at most 3 valid hits by confidence descending.
- A hit with an empty, non-http(s) or credential-bearing URL is dropped.
- The caller passes `Settings.min_confidence`. The module never reads the environment.
- ADR-0008 becomes `accepted` (front matter and index row). Its text says: `Citation` value object (law, article, paragraph, quote, confidence, source_url). Persistence is deferred until answers are stored. The change goes in this PR, because the issue requires it.
- Issue 122 text gets a Contract section and the fix of the importer: issue 111 imports `NOT_LEGAL_ADVICE_NOTICE`, and issue 121 renders citations (the issue names only 121).

## Consequences
- No migration, no dependency, effort S. Unit tests only, with an import test for the no-I/O rule.
- The stored `citation` table and the answer table wait for the answer-storage task (DBA notes: parent `answer` table, composite tenant FK, RLS, retention).
- A raw-score adapter must exist before issue 96 ships, or the rule gives meaningless results.
- Without a document version in the citation, a quote can go stale. Accepted risk.

## Types and order (lead, at refine, no design change)
- `Answer.citations` and `NoReliableAnswer.closest_sources` are `tuple[Citation, ...]`. `hits` is `Sequence[ScoredHit]`.
- Every hit's scores are validated before the URL filter drops any hit, so bad input never passes silently.
