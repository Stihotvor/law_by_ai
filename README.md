# Law by AI

![Docs Build](https://github.com/Stihotvor/law_by_ai/actions/workflows/ci.yml/badge.svg)

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

👉 See the [**project board**](https://github.com/Stihotvor/law_by_ai/issues)
for all active issues.
