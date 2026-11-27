# Path 1: Pure functional core

Core idea: `src/core/citations.py` holds frozen value types and one pure function `decide(hits, min_confidence) -> AnswerDecision`. It has no I/O import. The result carries an explicit refusal flag and the closest sources.

## Components
- `src/core/notices.py`: `NOT_LEGAL_ADVICE_NOTICE` (non-empty text, holds "not legal advice").
- `ScoredHit` (frozen): `source_url`, `quote`, `retrieval_score`, `rerank_score: float | None`. The search service (issue 96) adapts its hits to this type later.
- `Citation` (frozen): `source_url`, `quote`, `confidence`. Optional `law`, `article`, `paragraph` (assumption: `str | None`).
- `AnswerDecision` (frozen): `is_refusal`, `citations`, `closest_sources` (at most 3), `confidence`, `notice`.
- `decide(hits, min_confidence)`, `score(hit)`, `is_valid_url(url)`.

## Scoring rule
- No rerank score: confidence is the retrieval score.
- Both scores: `0.4 * retrieval + 0.6 * rerank` (weights are a guess until the evaluation runs). The result stays in [0, 1].
- Answer when the best valid confidence is `>= min_confidence`. Otherwise refuse.
- Invalid URL drops the hit. Bad score or bad `min_confidence` raises `ValueError` naming the field.

## Fit and risk
- No table, no migration, no new dependency. Effort S.
- Not handled: a caller that ignores `is_refusal`.
- Risk: the weights are untested. A hard `ValueError` on one bad hit fails the request, so the adapter must send clean data.
