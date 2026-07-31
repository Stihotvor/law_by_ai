# Law by AI

![Docs Build](https://github.com/Stihotvor/law_by_ai/actions/workflows/docs.yml/badge.svg)

AI-powered platform for legal document ingestion, processing, retrieval, and analysis.

## Documentation

The full project documentation is published on **GitHub Pages**:

👉 [**stihotvor.github.io/law_by_ai**](https://stihotvor.github.io/law_by_ai/)

| Page | Purpose |
|---|---|
| [**Intention doc**](https://stihotvor.github.io/law_by_ai/intention/) | Project scope, vision, and key decisions |
| [**Architecture**](https://stihotvor.github.io/law_by_ai/architecture/) | System design, plugin system, data flow |

## Architecture Overview

Law by AI uses a **plugin-based architecture** with 5 core plugin types:

| Plugin Type | Role | Default Implementation |
|---|---|---|
| **DatabasePlugin** | Document storage, full-text search | PostgreSQL |
| **VectorDBPlugin** | Semantic search via embeddings | Qdrant |
| **GraphDBPlugin** | Law article cross-reference graph | NetworkX (MVP) → Neo4j/Memgraph |
| **ETLSourcePlugin** | Fetch documents from external sources | Web ETL, Git ETL |
| **EmbeddingPlugin** | Generate text embeddings | Sentence Transformers |

A dynamic `PluginManager` loads and routes requests to the correct plugin,
making every backend swappable without changing agent logic.

## Status

Early implementation phase. The work is organized into **7 milestones**:

| Phase | Focus |
|---|---|
| **1 — Minimal Example** | End-to-end fetch → process → display |
| **2 — Foundation** | Plugin ABCs, PluginManager, models, config |
| **3 — Core Plugins** | PostgreSQL, Qdrant, NetworkX implementations |
| **4 — ETL & Embedding** | Web/Git ETL, Sentence Transformers |
| **5 — Agents** | All 6 agents (Fetcher, Processor, Researcher, etc.) |
| **6 — Tasks & UI** | Celery tasks + full Streamlit UI |
| **7 — Test & Polish** | Unit tests, integration tests, docs |

## Development

This project is managed with **[uv](https://docs.astral.sh/uv/)**. Install uv
globally (it is **not** a project dependency and must not be installed into the
project venv):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

uv creates and manages the project `.venv` for you — no manual
`python -m venv` or `source .venv/bin/activate` needed.

See [CONTRIBUTING.md](CONTRIBUTING.md) for full guidelines.

```bash
uv sync --extra dev --extra docs
```

```bash
uv run ruff check .          # lint
uv run ruff format --check . # format
uv run pytest                # tests
uv run mkdocs build --strict -f docs/mkdocs.yml # docs build
```

Two CI workflows run on PRs:
- **`ci`** — lint + tests, runs on any change outside `docs/`.
- **`docs`** — builds the docs, runs only on changes under `docs/` (with the
  config at `docs/mkdocs.yml`).

On `main`, the `docs` workflow also deploys the site to GitHub Pages.

👉 See the [**project board**](https://github.com/Stihotvor/law_by_ai/issues)
for all active issues.
