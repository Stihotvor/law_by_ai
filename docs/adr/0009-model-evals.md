---
status: proposed
---

# ADR-0009: Embedding/OCR/hybrid-search evaluation for Polish

## Context

The platform targets **Polish legal texts**. Embedding and OCR quality directly
drive search precision and document ingestion accuracy, yet the original plan
picked models without evidence. Hybrid search precision needs a measurable
target, and every model must fit the 4–6 GB RAM + SLM budget.

## Decision

- **Embedding evals**: compare candidate embedding models (e.g., Mistral embed,
  Gemini-mini embed 2, multilingual Sentence Transformers) on a Polish legal
  corpus. Choose by accuracy + RAM footprint; results live in `evals/`.
- **OCR evals**: compare OCR models (Tesseract, EasyOCR, PaddleOCR) on Polish
  scanned documents (diacritics, legal formatting). Choose by accuracy + speed
  + footprint.
- **Hybrid search evals**: build a labeled Polish legal query set; measure
  precision/recall of the hybrid retriever (FTS + semantic + re-rank + graph).
  Set and track targets (e.g., recall@10) with a baseline commit.
- Evaluations are reproducible scripts under `evals/`, not one-off notebooks.

## Consequences

- Model/retrieval choices become evidence-based rather than assumed.
- Some eval tooling and datasets are required early (Phase 3–4).
- Baseline numbers feed the SLA targets in ADR-0011.

## Alternatives Considered

- **Skip evals, ship defaults** — risks poor Polish retrieval and wasted
  re-embedding later.
- **Evals post-MVP** — re-embedding/re-OCR cost is high; doing it late is
  expensive.

## Related

- [Architecture](../architecture.md) — Embedding & OCR Models, `evals/`
- [Intention](../intention.md) #14, #20, #35
