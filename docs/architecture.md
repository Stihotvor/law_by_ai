---
status: draft
---

# System Architecture

> **Status:** Draft — reflects the plugin-based architecture planned in the
> [project milestones](https://github.com/Stihotvor/law_by_ai/issues?q=is%3Aissue+milestone%3A%22Phase+*%22).
> Aligns with the [Intention doc](intention.md).

---

## Overview

Law by AI is a self-hosted, multi-tenant platform for legal document ingestion,
processing, retrieval, and analysis. The system is built around a **plugin-based
architecture** where five core plugin types (Database, Vector DB, Graph DB,
ETL Source, Embedding) are loaded dynamically by a `PluginManager`.

All services run under Docker-Compose and communicate over the internal network.

```
┌──────────────────────────────────────────────────────────────────┐
│                         User (browser)                           │
└──────────────────────────┬───────────────────────────────────────┘
                           │ HTTP (Streamlit)
┌──────────────────────────▼───────────────────────────────────────┐
│                      Streamlit UI                                  │
│  (Fetch, Browse, Search, Analysis, Knowledge Graph, Changes)      │
└──┬────────────────────────────────────────────────────┬───────────┘
   │ Celery tasks (async)                               │ direct (UI)
┌──▼────────────────────────────────────────────────────▼───────────┐
│                        Agents Layer                                │
│  DocumentFetcherAgent · DocumentProcessorAgent · LegalResearchAgent│
│  ChangeTrackerAgent · KnowledgeGraphAgent · AnalysisAgent          │
└──┬────────────────────────────────────────────────────────────┬───┘
   │ uses plugins via PluginManager                              │
┌──▼────────────────────────────────────────────────────────────▼───┐
│                      PluginManager                                 │
│  (dynamic loading · type routing · lifecycle management)          │
└──┬─────┬──────┬──────┬──────────┬───────────────────────────────┬─┘
   │     │      │      │          │                               │
┌──▼──┐ ┌▼────┐ ┌▼───┐ ┌▼────────┐ ┌──────────────────────────┐  │
│DB   │ │VD   │ │Graph│ │ETL      │ │Embedding                 │  │
│Plugin│ │Plugin│ │Plugin│ │Source   │ │Plugin                   │  │
│     │ │     │ │     │ │Plugin   │ │                         │  │
└──┬──┘ └─┬───┘ └──┬──┘ └──┬─────┘ └──────────┬──────────────┘  │
   │      │        │       │                   │                 │
┌──▼──┐ ┌─▼────┐ ┌─▼────┐ │  ┌────────────────┐                │
│PG   │ │Qdrant│ │NX/   │ │  │Sentence         │                │
│     │ │      │ │Neo4j │ │  │Transformers     │                │
└─────┘ └──────┘ └──────┘ │  └────────────────┘                │
                          │  ┌──────────────┐                   │
                          └──┤Web / Git ETL │  (future plugins) │
                             └──────────────┘                   │
```

---

## Plugin Architecture

The system defines **five plugin types**, each with a dedicated ABC (abstract
base class). The `PluginManager` dynamically discovers, loads, and routes
requests to the correct plugin at runtime.

### 1. DatabasePlugin (`core/plugins/base.py`)

| Method | Purpose |
|---|---|
| `save_document` | Persist a `LegalDocument` |
| `get_document` | Retrieve by ID |
| `search_documents` | Full-text + metadata search |
| `get_recent_changes` | Diff-based version tracking |
| `delete_document` | Remove document and chunks |
| `update_document` | Partial update |

**Default implementation**: PostgreSQL plugin (`plugins/postgresql.py`).

### 2. VectorDBPlugin

| Method | Purpose |
|---|---|
| `upsert_embeddings` | Store/update chunk embeddings |
| `search_embeddings` | Semantic similarity search |
| `delete_embeddings` | Remove by chunk/filter |
| `create_collection` | New tenant collection |
| `delete_collection` | Remove tenant collection |

**Default implementation**: Qdrant plugin (`plugins/qdrant.py`).

### 3. GraphDBPlugin

| Method | Purpose |
|---|---|
| `add_node` | Insert a graph node (law article, citation) |
| `add_edge` | Create relationship (amends, refers-to, depends-on, cited-by) |
| `get_related_nodes` | Traverse relationships |
| `get_node` | Fetch single node |
| `delete_node` / `delete_edge` | Remove graph elements |
| `get_all_nodes` / `get_all_edges` | Bulk export |

**Default implementation**: NetworkX plugin (`plugins/networkx.py`).
**Production target**: Neo4j / Memgraph.

### 4. ETLSourcePlugin

| Method | Purpose |
|---|---|
| `fetch` | Pull documents from source |
| `validate_config` | Verify source credentials/URLs |
| `list_sources` | Enumerate available sources |

**Implementations**: Web ETL (`plugins/web_etl.py`), Git ETL (`plugins/git_etl.py`).

### 5. EmbeddingPlugin

| Method | Purpose |
|---|---|
| `generate_embeddings` | Convert text → vector |
| `get_model_info` | Report model name / version |
| `get_embedding_dimension` | Return vector dimension |

**Default implementation**: Sentence Transformers (`plugins/sentence_transformers.py`).

### PluginManager (`core/plugins/manager.py`)

- **Dynamic loading** via `importlib` — plugins are auto-discovered from the
  `plugins/` directory.
- **Type routing** — `get_plugin(type)` returns the correct initialized plugin.
- **Configuration-based** — plugin selection driven by `config/settings.py`.
- **Lifecycle** — `initialize()` → use → `close()` for clean shutdown.
- **Singleton** — global `plugin_manager` instance.

---

## Services

### 1. Streamlit UI

- **Role**: Primary user interface — fetch, browse, search, analysis, knowledge
  graph, changes tracking.
- **Pages planned**:
  - **Fetch Documents** (P1) — trigger ETL, upload files
  - **Browse Documents** (P1) — list, filter, view metadata
  - **Search** (P1) — keyword + semantic + hybrid
  - **Analysis** (P2) — impact, compliance, citation
  - **Knowledge Graph** (P2) — visual exploration
  - **Changes Tracking** (P2) — diff-based version comparison
- **Frameworks**: Streamlit + custom components.
- **No public API** — API clients fetch data from the UI/backend directly.

### 2. Agents Layer

Each agent is a Python class that consumes one or more plugins via the
`PluginManager`. Agents are invoked by Celery tasks (async) or directly
from the UI (synchronous).

| Agent | Responsibility | Plugins Used |
|---|---|---|
| **DocumentFetcherAgent** | Pull documents from ETL sources, run OCR, store raw text | ETLSourcePlugin, DatabasePlugin |
| **DocumentProcessorAgent** | Chunk, embed, store vectors + metadata, build graph edges | DatabasePlugin, VectorDBPlugin, GraphDBPlugin, EmbeddingPlugin |
| **LegalResearchAgent** | Multi-source legal Q&A via hybrid RAG + graph-guided retrieval | VectorDBPlugin, GraphDBPlugin, EmbeddingPlugin |
| **ChangeTrackerAgent** | Diff-based version tracking across document versions | DatabasePlugin, GraphDBPlugin |
| **KnowledgeGraphAgent** | Parse citations, build law/article dependency graphs | GraphDBPlugin, DatabasePlugin |
| **AnalysisAgent** | Impact analysis, compliance checking, citation analysis | VectorDBPlugin, GraphDBPlugin, EmbeddingPlugin |

- **Execution model**: Human-in-the-loop — user triggers or approves each step.
- **Pre-configured pipelines** for the MVP.

### 3. Celery + Redis

- **Role**: Async task queue for long-running operations (document fetching,
  processing, analysis).
- **Broker**: Redis.
- **Result backend**: Redis (MVP) → PostgreSQL (production).
- **Tasks**: Wrappers around agent methods (e.g., `fetch_document`,
  `process_document`, `track_changes`).

### 4. PostgreSQL

- **Role**: Primary relational store.
- **Stores**: Users, tenants, document metadata, text chunks, annotations,
  processing state, full-text search index.
- **Accessed via**: `DatabasePlugin`.

### 5. Qdrant (MVP) → Production

- **Role**: Vector store for semantic search.
- **Data**: Document chunk embeddings.
- **Multi-tenant**: Separate collection per tenant (or partition key).
- **Accessed via**: `VectorDBPlugin`.

### 6. NetworkX (MVP) → Neo4j / Memgraph (Production)

- **Role**: Graph store for cross-reference tracking.
- **Data**: Law articles and their relationships (amends, refers-to, depends-on,
  cited-by).
- **Migration**: NetworkX in-process for MVP, then Neo4j or Memgraph with
  Cypher query support.
- **Accessed via**: `GraphDBPlugin`.

---

## Data Flow

### Document Ingestion

```
Source (PDF / DOCX / HTML / Web / Git)
         │
         ▼
  ┌──────────────┐
  │ ETLSource    │  ← Web ETL Plugin / Git ETL Plugin
  │ Plugin       │
  └──────┬───────┘
         │ raw text
         ▼
  ┌──────────────────┐
  │ DocumentFetcher  │  ← Agent (via Celery task)
  │ Agent            │
  └──────┬───────────┘
         │ LegalDocument
         ▼
  ┌──────────────────┐
  │ DatabasePlugin   │  → PostgreSQL (save document metadata)
  └──────┬───────────┘
         │
         ▼
  ┌──────────────────┐
  │ DocumentProcessor│  ← Agent
  │ Agent            │
  └──┬───────┬───────┘
     │       │
     ▼       ▼
  Embedding    Graph
  Plugin      Plugin
     │           │
     ▼           ▼
  VectorDB    GraphDB     Database
  Plugin      Plugin      Plugin
  (Qdrant)    (NX/Neo4j)  (PG: chunks)
```

1. **ETL Source Plugin** fetches raw text from the source (web, Git, file, API).
2. **DocumentFetcherAgent** runs OCR if needed, wraps the result in a
   `LegalDocument` model, and persists it via `DatabasePlugin`.
3. **DocumentProcessorAgent** chunks the text, generates embeddings via
   `EmbeddingPlugin`, stores vectors via `VectorDBPlugin`, and builds graph
   edges via `GraphDBPlugin`.

### Search & Q&A

```
User Query
    │
    ▼
┌──────────────────────┐
│ Hybrid Retriever      │
│ (keyword + semantic)  │
└──┬─────────┬──────────┘
   │         │
   ▼         ▼
Database   VectorDB
Plugin     Plugin
(Postgres  (Qdrant
 FTS)       sim search)
   │         │
   └────┬────┘
        ▼
┌──────────────┐
│ Re-ranker     │  (cross-encoder)
└──────┬───────┘
       │
       ▼
┌──────────────────┐
│ Graph-Guided     │  GraphDBPlugin (Neo4j traversal)
│ Multi-Hop        │
└──────┬───────────┘
       │
       ▼
┌──────────────────────────────────────┐
│ Context + Prompt → liteLLM → LLM     │
│ → Answer + Citations                  │
└──────────────────────────────────────┘
```

---

## Directory Structure

```
law_by_ai/
├── core/
│   ├── __init__.py
│   └── plugins/
│       ├── __init__.py
│       ├── base.py          # Plugin ABCs (all 5 types)
│       ├── manager.py       # PluginManager (dynamic loading)
│       ├── exceptions.py    # Plugin-specific errors
│       └── utils.py         # Shared utilities
├── plugins/                 # Concrete plugin implementations
│   ├── postgresql.py
│   ├── qdrant.py
│   ├── networkx.py
│   ├── web_etl.py
│   ├── git_etl.py
│   └── sentence_transformers.py
├── agents/
│   ├── document_fetcher.py
│   ├── document_processor.py
│   ├── legal_research.py
│   ├── change_tracker.py
│   ├── knowledge_graph.py
│   └── analysis.py
├── tasks/                   # Celery task definitions
│   ├── celery_app.py
│   └── etl_tasks.py
├── ui/                      # Streamlit pages
│   ├── app.py
│   ├── pages/
│   │   ├── fetch.py
│   │   ├── browse.py
│   │   ├── search.py
│   │   ├── analysis.py
│   │   ├── knowledge_graph.py
│   │   └── changes.py
│   └── components/
├── config/
│   ├── settings.py          # Environment-based configuration
│   ├── plugins.py           # Plugin registration
│   └── .env.example
├── data/                    # Data models
│   └── models.py            # LegalDocument, DocumentChunk, GraphNode, AnalysisResult
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
├── tests/
│   ├── test_plugins/
│   ├── test_agents/
│   └── test_tasks/
├── scripts/
├── docs/                    # mkdocs documentation
├── requirements.txt
└── README.md
```

---

## Multi-Tenant Isolation

- **Row-level isolation** in PostgreSQL — every document, chunk, and user
  record carries a `tenant_id`.
- **Separate collection per tenant** in Qdrant (or partition key).
- **Subgraph per tenant** in Neo4j (label-based).
- Tenant context is threaded through agents and plugins via the `tenant_id`
  field.

---

## Data Model (Conceptual)

```
Tenant
  ├── User
  ├── Document (LegalDocument)
  │     ├── metadata (title, date, source, type, jurisdiction)
  │     ├── Chunk[] (DocumentChunk)
  │     │     ├── text
  │     │     ├── embedding (→ VectorDBPlugin)
  │     │     └── position (page, offset)
  │     └── GraphNode (→ GraphDBPlugin)
  │            ├── article_id
  │            └── relationships: amends, refers-to, depends-on, cited-by
  └── Query / Session log
```

---

## Technology Stack

| Layer | MVP | Production |
|---|---|---|
| **UI** | Streamlit | Streamlit |
| **Task queue** | Celery + Redis | Celery + Redis |
| **Plugin system** | PluginManager (dynamic loading) | PluginManager |
| **Relational DB** | PostgreSQL (via DatabasePlugin) | PostgreSQL |
| **Vector store** | Qdrant (via VectorDBPlugin) | Qdrant |
| **Graph store** | NetworkX (via GraphDBPlugin) | Neo4j / Memgraph |
| **Embeddings** | Sentence Transformers (via EmbeddingPlugin) | Same |
| **LLM gateway** | liteLLM proxy | liteLLM proxy |
| **OCR** | Tesseract | Tesseract |
| **Deployment** | Docker-Compose | Docker-Compose |

---

## Implementation Phases

The work is tracked in [7 milestones](https://github.com/Stihotvor/law_by_ai/milestones):

| Phase | Focus | Key Issues |
|---|---|---|
| **1 — Minimal Example** | End-to-end fetch → process → display | Streamlit (P0), Celery (P0), simplified agents |
| **2 — Foundation** | Plugin ABCs, PluginManager, models, config, utilities | Issues #14–#18 |
| **3 — Core Plugins** | PostgreSQL, Qdrant, NetworkX | Issues #19–#21 |
| **4 — ETL & Embedding** | Web/Git ETL, Sentence Transformers | Issues #22–#24 |
| **5 — Agents** | All 6 agents built on plugin system | Issues #25–#30 |
| **6 — Tasks & UI** | Full Celery app, all Streamlit pages | Issues #31–#39 |
| **7 — Test & Polish** | Unit tests, integration tests, docs, examples | Issues #40–#43 |

---

## Migration Paths

1. **Plugin implementations** can be swapped without changing agent code —
   the `PluginManager` abstraction makes each backend replaceable.
2. **NetworkX → Neo4j/Memgraph**: Implement a `Neo4jPlugin` that satisfies
   the same `GraphDBPlugin` ABC. Export existing graph data and swap the
   config.
3. **Manual → Automated legal updates**: Celery Beat schedule replaces
   manual triggers.

---

## Future Considerations

- **Public API server** (FastAPI) for third-party integrations.
- **Additional plugin types** (e.g., OCR plugin, notification plugin).
- **Annotations and comments** on documents.
- **Collaboration features** (shared tenants).
- **Multi-language UI** (Ukrainian, Polish).
- **Automated legal-update fetching** via Celery Beat.
