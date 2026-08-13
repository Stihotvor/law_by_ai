# Law by AI

![Docs Build](https://github.com/Stihotvor/law_by_ai/actions/workflows/docs.yml/badge.svg)

AI-powered platform for legal document ingestion, processing, retrieval, and analysis.

## Documentation

The full project documentation is published on **GitHub Pages**:

👉 [**stihotvor.github.io/law_by_ai**](https://stihotvor.github.io/law_by_ai/)

| Page | Purpose |
|---|---|
| [**Intention doc**](https://stihotvor.github.io/law_by_ai/intention/) | Project scope, vision, and key decisions |
| [**Architecture**](https://stihotvor.github.io/law_by_ai/architecture/) | System design, direct integrations, data flow |
| [**Migrations**](https://stihotvor.github.io/law_by_ai/migrations/) | Alembic schema migration commands |

## Architecture Overview

Law by AI uses **direct integrations** — PostgreSQL is the hardcoded relational
store, accessed via `PostgreSQLStore` and managed with **Alembic migrations**
(issue #9). The protocol-based plugin system is **deprecated** (ADR-0014).

| Store / Model | Role | Implementation |
|---|---|---|
| **PostgreSQL** | Document storage, users/tenants, full-text search | Direct (`PostgreSQLStore`) + Alembic migrations |
| **Qdrant** | Semantic search via embeddings | Direct client (planned) |
| **Neo4j AuraDB** | Law article cross-reference graph | Direct client (planned) |
| **LLM/SLM** | Q&A, analysis | OpenAI-compatible endpoints, per-agent models |
| **Reranking** | Hybrid search precision | Cohere |

See [ADR-0014](docs/adr/0014-hardcoded-postgresql.md) for the deprecation
decision and [Migrations](docs/migrations.md) for schema commands.

## Status

Early implementation phase. The work is organized into **7 milestones**:

| Phase | Focus |
|---|---|---|
| **1 — Minimal Example** | End-to-end fetch → process → display |
| **2 — Foundation** | Data store, models, config, migrations |
| **3 — Core Integrations** | PostgreSQL store, Qdrant, Neo4j |
| **4 — ETL & Embedding** | Web/Git ETL, embedding provider |
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
- **`ci`** — lint, typecheck, security scan, unit tests, and Docker integration
  tests. Runs on any change outside `docs/`.
- **`docs`** — builds the docs, runs only on changes under `docs/` (with the
  config at `docs/mkdocs.yml`).

On `main`, the `docs` workflow also deploys the site to GitHub Pages.

## Docker

The full stack runs under Docker Compose:

```bash
docker compose -f docker/docker-compose.yml up --build
```

| Service | Description |
|---|---|
| `app` | Streamlit UI — http://localhost:8501 |
| `celery-worker` | Celery worker (Redis broker, concurrency 2) |
| `postgres` | PostgreSQL (PostgreSQLStore) |
| `redis` | Celery broker / result backend |

Stop it with `docker compose -f docker/docker-compose.yml down`. Postgres data
persists in the `pgdata` volume.

Development (fast feedback)

A small dev-only override is provided at `docker/docker-compose.dev.yml`. It
mounts the host `src/` into the running containers so Python/Streamlit code
changes are picked up without rebuilding the image.

Two-file explicit (recommended):

```bash
docker compose -f docker/docker-compose.yml -f docker/docker-compose.dev.yml up --build
```

One-liner using COMPOSE_FILE (no -f flags):

```bash
COMPOSE_FILE=docker/docker-compose.yml:docker/docker-compose.dev.yml docker compose up --build
```

Auto-merge when working in the `docker/` dir (override filename):

```bash
# rename to enable automatic merging when running compose in docker/
# (optional)
mv docker/docker-compose.dev.yml docker/docker-compose.override.yml
cd docker && docker compose up --build
```

Notes:
- Build once with `--build`; subsequent `up` runs will use the mounted source and
  avoid full image rebuilds for code-only changes.
- The `app` (Streamlit) reloads on file changes automatically. The runtime
  `celery-worker` image does not include dev-only autoreload tooling; restart
  the worker after code changes or run a different dev image if you need
  worker autoreload.

Run the test suite against live postgres and redis (no app/worker started):

```bash
docker compose --profile test -f docker/docker-compose.yml run --rm test
```

👉 See the [**project board**](https://github.com/Stihotvor/law_by_ai/issues)
for all active issues.
