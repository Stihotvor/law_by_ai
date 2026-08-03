# Agents

Business logic of the platform. Each agent is a Python class that consumes one
or more plugins through the `PluginManager`, invoked asynchronously via Celery
tasks or synchronously from the UI. Human-in-the-loop: users trigger or approve
each step.

- `document_fetcher.py` — fetch + OCR + persist
- `document_processor.py` — chunk, embed, store vectors, build graph edges
- `legal_research.py` — answer questions with citations + confidence
- `change_tracker.py` — document diffs (ADR-0007)
- `knowledge_graph.py` — citation parsing, dependency graph
- `analysis.py` — impact / compliance / citation analysis
- `bureaucracy_assistant.py` — step-by-step administrative procedures (ADR-0008)
