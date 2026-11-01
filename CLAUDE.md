# law_by_ai

Python 3.13 AI legal document platform (Streamlit, Celery, SQLAlchemy, PostgreSQL, Redis).
Repo: `Stihotvor/law_by_ai` (public, default branch `main`). GitHub Project 5 "Law by AI" is the board.

## Environment
- Venv: `.venv` (created with uv). Use `.venv/bin/python` and `.venv/bin/pytest`.
- Dependencies come from `pyproject.toml`. Dev tools: `uv pip install --python .venv/bin/python -e ".[dev]"`.
- Fast tests: `.venv/bin/pytest -m "not integration"` (54 pass).
- Full suite (67 pass): `docker compose --profile test -f docker/docker-compose.yml run --rm test`. It needs `docker/.env` (copy of `docker/.env.example`, gitignored). Rebuild the image with `build --no-cache test` after pulling, or the container runs stale code.
- Quality tools in `.venv`: ruff, pyright, bandit, pip-audit, pre-commit. CI runs lint, typecheck, security scan, unit tests, Docker integration tests.
- Services: `docker/docker-compose.yml` (postgres, redis, app, celery-worker, test). Stop with `docker compose -f <abs path>/docker/docker-compose.yml down`.
- Migrations: Alembic (`alembic.ini`, `migrations/`, `docs/migrations.md`).
- Branches: `feature/`, `fix/`, `docs/` named after the issue. PR body has `Closes #N` or `Refs #N`. See `CONTRIBUTING.md`.

## Layout
`src/` (agents, config, core, data, evals, plugins, storage, tasks, ui), `tests/` (unit, integration), `docs/` (mkdocs + ADRs), `docker/`, `scripts/seed_db.py`.

## Product (docs/intention.md is the charter)
Self-hosted, multi-tenant AI lawyer for EU (Poland) citizens and expats. Areas: family, child care, taxes, anti-xenophobic law. It must not bypass the law.
- Hard budget: runs fast on 4-6 GB RAM with a small local model.
- MVP must have: citations with confidence scores and source links, faceted filters, document diffs (Git-backed), bureaucracy assistant, observability, health checks, auth + RBAC, tenant leak tests.
- Human-in-the-loop agents, pre-configured pipelines, English docs first, MIT license, invite-only contributions.
- Targets (stated in the charter, may be outdated): MVP end of next month, v1 end of this year.

## Architecture (docs/architecture.md, ADRs in docs/adr/)
- ADR-0014 (accepted): PostgreSQL is a hardcoded integration (`PostgreSQLStore`, `src/plugins/relational_db/postgres.py`). The plugin system (ADR-0001) is deprecated and each backend becomes a direct integration.
- ADR-0013 (accepted): auth with streamlit-authenticator, bcrypt, signed cookie. RBAC: `admin` manages data, `user` is read-only (`src/core/security/`).
- Planned stores: Qdrant (vectors), Neo4j AuraDB Free (graph), Cohere rerank, OpenAI-compatible LLM per agent, dedicated embedding provider.
- Multi-tenancy: shared documents, per-tenant data isolated by `tenant_id` and PostgreSQL RLS (ADR-0003).
- Celery + Redis, failed tasks persisted in DB, user re-runs from UI (ADR-0006). Observability: structlog + OTel to Grafana Alloy (ADR-0005).
- ADRs 0002-0012 are still `proposed`. ADR-0001 is superseded.

## Current state (as of 2026-10-31)
Built: PostgreSQL store (CRUD, ILIKE search), RBAC helpers and tenant helpers in `src/core/security/`, Celery app shell, Streamlit app shell, settings (plain class, still has Cohere rerank keys), Alembic initial migration, Docker stack, CI.
Verified gaps (2026-11-01): no login UI (`src/ui/components/auth.py` is missing), no RLS or cross-tenant tests (RLS policies exist only on `tenants` and `users`, not on `legal_document`), no `status` column on `legal_document`, no full-text search, no Postgres image file.
Not built: all agents (`src/agents/` is empty), Qdrant, Neo4j, ETL sources, embeddings, OCR, search, observability, health checks, most UI pages.

## Wave 1 MVP plan (2026-11-01)
Requirements, a 43-task DAG and 43 tickets are in `docs/design/wave1-mvp/` (`requirements.md`, `dag.md`, `tickets/`). The planning date for the MVP is 2027-02-28. Rerank is local (Cohere dropped), and the model is chosen by the #58r eval. The backlog below is the state before this plan. #14 and #15 are closed, 14 issues were added to the board, and #85 (PostgreSQL FTS) was created.

## Delivery backlog (GitHub, 48 open issues as of 2026-11-01, 7 milestones, none have due dates)
P0 = must for MVP. Issues marked * are not on the project board.
- **Phase 1 Minimal Example** (4 open): #10 DocumentFetcherAgent (simple), #11 Celery fetch_document task, #12 minimal Streamlit fetch page, #13 requirements + Dockerfile. 18 items closed.
- **Phase 2 Foundation**: #14 protocols, #15 PluginManager, #16 data models, #17 core utils, #18 full settings, #52 JWT auth + RBAC (P0).
- **Phase 3 Core Plugins**: #19 PostgreSQL full CRUD + FTS, #20 Qdrant, #21 Memgraph/Neo4j.
- **Phase 4 ETL and Embedding**: #22 Web ETL, #23 Git ETL, #24 embedding plugin, *#58 embedding eval (Polish), *#59 OCR eval, *#64 target lite LLMs.
- **Phase 5 Agents**: #25 Fetcher, #26 Processor, #27 LegalResearch, #28 ChangeTracker, #29 KnowledgeGraph, #30 Analysis, *#61 Bureaucracy assistant (P0), *#63 citations with confidence (P0).
- **Phase 6 Tasks and UI**: #31 Celery config + ETL tasks, #32 analysis tasks, #33-#38 UI pages (fetch, browse, search, changes, graph, analysis), #39 entry point, *#54 health checks, *#55 observability, *#56 failed-task registry + re-run, *#62 faceted filters (P0).
- **Phase 7 Test and Polish**: #40 plugin tests, #41 agent tests, #42 integration tests, #43 plugin examples, *#49 architecture docs, *#51 ADR register, *#53 tenant leak tests, *#57 efficiency budget + SLA (P0), *#60 hybrid search eval.
- Closed so far: #1-#9 (scope, research, architecture, CI, license, repo + Docker, settings, plugin SPI, PostgreSQL basic CRUD).
- Open PRs: six dependabot bumps (#77 pyjwt, #78 urllib3, #81 pillow, #82 virtualenv, #83 filelock, #84 gitpython).

## Known drift (verify before work)
These are my reading of docs against issues. Check each one with the user before acting.
- Phase 2 issues #14, #15 and Phase 3 #19, #21 describe the old plugin and Memgraph design. ADR-0014 and the charter replaced them (direct integrations, Neo4j AuraDB). Several are probably obsolete or need rewrite.
- #52 was rewritten on 2026-11-01 from JWT to the streamlit-authenticator login UI (ADR-0013). The auth and RLS tests do NOT exist yet (see #53b in the Wave 1 plan).
- Issue #51 asks for ADRs 0001-0011. The repo already has ADRs 0001-0014.
- README table says "Phase 3 Core Integrations" and the GitHub milestone says "Core Plugins".
- Issues use "Todo" only on the board. No issue is marked In Progress.

## Working rules for this repo
- Git remote operations (clone, push, `gh`) go through the `git-agent` subagent. A hook blocks `.env` access and pipes in Bash.
- Quality gate before a task is done: ruff check, ruff format --check, pyright, pytest.
