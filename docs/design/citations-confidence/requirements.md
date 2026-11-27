# Requirements: citations-confidence

Source: the issue "Citations with confidence". Facts come from `src/config/settings.py`, `src/data/models.py`, `docs/adr/0008-mvp-scope.md`, `docs/adr/0015-information-only-answers.md` and `docs/architecture.md`.

## Business Goals
- Every answer shows source links and a confidence score. A low score gives "no reliable answer" and the closest sources (ADR-0008, ADR-0015). Today no citation model and no scoring rule exist.
- The bureaucracy agent needs three things from this task: the constant `NOT_LEGAL_ADVICE_NOTICE`, a score for each citation, and one refusal result that holds the closest sources. It imports them and does not copy them.
- The research and analysis agents use the same result. The citation render UI uses it too. The shared notice text lives in one place.
- Decided (G1, 2026-11-27: path 1 with review changes): a pure core module `src/core/citations.py` with the citation value object, the scoring rule and the decision "answer or no reliable answer". A second module `src/core/notices.py` holds the notice constant.

## Technical Constraints
- Python 3.13. No new dependency. No LLM call, no HTTP call and no database call inside the module.
- The hybrid search service (issue 96) is not built. The module takes its own small input type: a source URL, a quote, a retrieval score and an optional rerank score. The search service adapts its hits to this type later.
- Value objects follow the project style: `@dataclass(frozen=True)`.
- `min_confidence` comes from `Settings.min_confidence` (default 0.5, range 0.0 to 1.0). The caller passes the value in. The module does not read the environment.
- The scoring rule is documented in the module docstring and in the ADR text. It is deterministic.
- ADR-0008 changes from `proposed` to `accepted` in its front matter and in the index row. The ADR text is updated: the `Citation` entity is a value object (law, article, paragraph, confidence, source_url), not a table.
- A table or a migration is out of scope. No answer is stored in this task.
- Budget: 4-6 GB RAM host. The scoring uses no model.
- Non-goals: UI, LLM answer text, search, rerank model choice, storing citations.

## Edge Cases
- Hit list is empty: the result is `NoReliableAnswer` with no sources.
- Confidence exactly equal to `min_confidence`: normal answer (the rule is `>=`).
- Confidence 0.4 with `min_confidence` 0.3: normal answer. With 0.5: "no reliable answer".
- Score outside [0, 1] or not a number (NaN, infinity, bool): `ValueError` that names the field. The module does not clip silently.
- Source URL empty, not http or https, or holding credentials: the hit is not a citation. It counts as "no citation".
- Hit with no rerank score: the retrieval score is the confidence.
- Scores are already in [0, 1]. A raw Qdrant cosine or a logit is the adapter's problem (issue 96).
- All hits lack a valid citation: "no reliable answer". The closest sources list is empty.
- `min_confidence` outside [0, 1]: `ValueError`.
- Closest sources: at most 3, sorted by confidence, highest first. A tie keeps the input order.

## Failure Modes
- The module raises only `ValueError` for bad input. It never returns a normal answer on bad input.
- A caller that ignores the refusal result must not show a score above the threshold as fact. The result is a union `Answer | NoReliableAnswer`. The refusal type has no citations and no confidence, so a caller cannot read an answer from a refusal.
- The notice constant is never empty. A test fails when the text does not hold "not legal advice" (case-insensitive).
- The user sees "no reliable answer" and the closest sources. The user never sees a raw score below the threshold as an answer.

## Success Metrics
1. 100% of citations from the scorer have a valid `source_url` and a confidence in [0, 1] (unit test over 4 or more hit sets).
2. 6 of 6 acceptance scenarios in the issue pass as unit tests: valid citations, below threshold, no citation, setting changes outcome, shared notice, ADR status.
3. Boundary tests pass at confidence 0.5 (answer), 0.49 (refusal), 0.4 with threshold 0.3 (answer).
4. The module imports no database, network or LLM package (an import test checks it).
5. Quality gate: ruff check, ruff format --check, pyright and pytest all pass. Unit coverage of the two new modules is 100% of lines.
6. OPEN: the weight between retrieval score and rerank score cannot be tuned before issue 96 and an evaluation exist. The first rule is fixed and documented. Risk accepted: the rule may change when the evaluation runs.
