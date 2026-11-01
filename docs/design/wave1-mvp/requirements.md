# Wave 1 MVP requirements (law_by_ai)

Date: 2026-11-01. Source: decisions of the product owner. Scope: Wave 1 DAG (`dag.md`).

## Business Goals

- Users: EU (Poland) citizens and expats. First real users: invite-only testers.
- North-star metric (charter): time and money saved per user.
- MVP planning date: 2027-02-28. The date 2026-11-30 from the charter is dropped. The date moves before scope does.
- Legal-advice boundary: information only. Every answer shows citations and the fixed notice "not legal advice". No personal legal conclusions.
  - Test: an answer view without the notice fails the UI test.
- Bureaucracy procedures (W1-61a) show a source link, a last-checked date and a "verify with the office" line on every step.
- Decided: invite-only testers, information-only answers, planning date 2027-02-28.

## Technical Constraints

- Budget: 4-6 GB RAM with a small local model (ADR-0011, charter). Hosting: Docker Compose, self-hosted.
- Stack unchanged: PostgreSQL (direct), Qdrant, Neo4j AuraDB Free, Celery + Redis, Streamlit, OpenAI-compatible LLM per agent.
- Polish full-text search uses a Polish hunspell dictionary in the Postgres image (W1-85).
  - OPEN: the dictionary adds image and build work. Fallback if it overruns: `simple` + `unaccent`. Needs owner approval before the switch.
- Query languages: Polish, English, Ukrainian. The embedding eval (W1-58) tests all three.
- Scanned documents are in the MVP. OCR engine is chosen by W1-59 and built before the MVP date. W1-59 moves from the parallel track into Wave 1.
- Rerank runs locally (W1-35a). Cohere is dropped, so no query or chunk leaves the host. Primary model: BAAI/bge-reranker-v2-m3 (int8 ONNX, Apache-2.0). Fallback: Horizon-Labs/multilingual-reranker-small (int8 ONNX, 268 MB, Apache-2.0).
  - The final choice comes from an eval inside W1-58: both models and no rerank, recall@5 per language (Polish, English, Ukrainian), and latency for 20-50 pairs under 500 ms on CPU. No model enters the code before that eval.
  - Cloudflare Clef / Clef-flash was checked. It is a decision model, not a reranker, and too large for the 4-6 GB budget. Possible later use: an answerability check for W1-63a. Out of the MVP.
- Sample corpus: about 50 public Polish law texts, by area (family, child care, tax, residence). Every download needs owner approval.
- Proposed ADRs 0003, 0005, 0006, 0008 and 0011 become accepted in the PR that implements each.
  - OPEN: not asked in the session. Default applied. Owner must confirm.
- ADR-0003 still names Chroma and Memgraph. Fix the text in the PR that accepts it.
- Decided: stack unchanged, hunspell FTS, three languages, OCR in MVP, Cohere required, public corpus.

## Edge Cases

- A query in Ukrainian or English must find Polish source text (cross-language search).
  - Test: a Ukrainian question returns the expected Polish law article in the top 5 of the eval set.
- A scanned PDF is processed through OCR and enters the same review queue as a text document.
- A new document stays `needs_review` until an admin approves it in the review queue (W1-26c, new task). Users never see unapproved documents.
- A user with role `user` never sees write actions (approve, re-run, fetch). Role `admin` sees them.
- Tenant A never reads or writes tenant B rows (RLS already exists in the initial migration).
  - Test: W1-53b integration test shows 0 cross-tenant rows.
- Query with no matching source returns "no reliable answer" and the closest sources.
- W1-22b only stores a content hash and a version stub. Full Git diffs wait for Wave 2 (W1-28).
  - OPEN: not asked in the session. Default applied. Owner must confirm.
- Decided: cross-language queries, OCR inputs, review queue, role limits, tenant isolation.

## Failure Modes

- The local rerank model is missing or fails to load: search returns an explicit error (hard error, owner decision 2026-11-01). No silent fallback.
  - Test: with the rerank model missing, the search service returns an explicit error and the page shows it.
  - A slow rerank call is not a failure. The 500 ms limit is a performance test, not a runtime switch.
- An admin rejects a document in the review queue (W1-26c): the document, its chunks and its Qdrant points are deleted (owner decision 2026-11-01). Proposed: an audit row (document id, source URL, admin, time) so the same source is not fetched again. Owner confirmation pending.
- Existing documents are backfilled as `approved` by W1-26m. W1-12 (fetch page) is admin only, through W1-52b.
- Confidence below the threshold, or no citation: the user sees "no reliable answer" plus the closest sources. The threshold (start value 0.5) is a setting. The eval W1-61d tunes it.
- A failed ingest or Celery task writes a row with traceback and arguments to the failed-task table (W1-56a). An admin re-runs it from the UI (W1-56b). W1-56 stays complete in the MVP.
- Wrong or stale bureaucracy step: the owner reviews every source and step of the seed procedures before merge (W1-61a). A lawyer review comes before v1.
- Scope or date overrun: the date moves and the scope stays. The orchestrator reports the new date at each phase.
- Decided: hard fail for rerank, refusal below threshold, full failed-task registry, owner review of procedures.

## Success Metrics

- Retrieval: recall@5 >= 0.80 on the Polish sample for the chosen model and hybrid search, measured per query language (Polish, English, Ukrainian). Source: W1-58 and W1-85 evals.
- Citations: 100% of shown answers carry an openable source link. At least 90% of answers in the W1-61d eval (10 or more questions) are judged correct by the owner.
- Performance: p95 hybrid search latency < 3 s.
- Memory: peak RAM <= 6 GB under `mem_limit: 6g`. Source: W1-57a.
- Isolation: 0 cross-tenant rows in the W1-53b leak test.
- Planning date: MVP by 2027-02-28.
- Quality gate on every code task: `ruff check`, `ruff format --check`, `pyright`, `.venv/bin/pytest -m "not integration"` all pass.

## Open items

- OPEN: hunspell dictionary cost. Fallback `simple` + `unaccent`. Owner approves the switch.
- Closed: Cohere data-leaves-host risk. Rerank is local. Rerank model choice stays open until the W1-58 eval.
- Closed: rerank failure behavior is a hard error.
- OPEN: reference CPU for the 500 ms rerank limit. Not named yet. W1-58r prints the CPU model.
- OPEN: ADR acceptance inside the implementing PR (default applied, not confirmed).
- OPEN: W1-22b stub versioning (default applied, not confirmed).
- OPEN: the planning date 2027-02-28 has not been checked against the resized DAG.
