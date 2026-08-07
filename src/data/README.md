# Data models

Core domain models:

- `LegalDocument`, `DocumentChunk` — documents and their chunks
- `GraphNode` — law articles + relationships (amends, refers-to, depends-on,
  cited-by)
- `Citation` — law, article, paragraph, confidence, source_url (ADR-0008)
- `AnalysisResult` — agent analysis output
- `FailedTask` — in-DB failure registry (ADR-0006)
- `Note` / `Chat` — per-tenant state
