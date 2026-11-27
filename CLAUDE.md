# law_by_ai

Python 3.13 AI legal document platform (Streamlit, Celery, SQLAlchemy, PostgreSQL, Redis).
Repo: `Stihotvor/law_by_ai` (public, default branch `main`). GitHub Project 5 "Law by AI" is the board.

## Environment
- Venv: `.venv` (created with uv). Use `.venv/bin/python` and `.venv/bin/pytest`.
- Dependencies come from `pyproject.toml`. Dev tools: `uv pip install --python .venv/bin/python -e ".[dev]"`.
- Fast tests: `.venv/bin/pytest -m "not integration"`.
- Full suite: `docker compose --profile test -f docker/docker-compose.yml run --rm test`. It needs `docker/.env` (copy of `docker/.env.example`, gitignored). Rebuild the image with `build test` after pulling, or the container runs stale code. Use `--no-cache` only to debug a stale layer, because every uncached build adds to the Docker build cache.
- Quality tools in `.venv`: ruff, pyright, bandit, pip-audit, pre-commit. CI runs lint, typecheck, security scan, unit tests, Docker integration tests.
- Services: `docker/docker-compose.yml` (postgres, redis, app, celery-worker, test). Stop with `docker compose -f <abs path>/docker/docker-compose.yml down`.
- Migrations: Alembic (`alembic.ini`, `migrations/`, `docs/migrations.md`).
- Branches: `feature/`, `fix/`, `docs/` named after the issue. A new ADR goes in its own PR on an `adr/` branch, and the PR title starts with `ADR: `. PR body has `Closes #N` or `Refs #N`. See `CONTRIBUTING.md`.

## Layout
`src/` (agents, config, core, data, evals, plugins, storage, tasks, ui), `tests/` (unit, integration), `docs/` (mkdocs + ADRs), `docker/`, `scripts/seed_db.py`.

## Product (docs/intention.md is the charter)
Self-hosted, multi-tenant AI legal assistant (information, not advice) for EU (Poland) citizens and expats. Areas: family, child care, taxes, anti-xenophobic law. It must not bypass the law.
- Hard budget: runs fast on 4-6 GB RAM with a small local model.
- MVP must have: citations with confidence scores and source links, faceted filters, document diffs (Git-backed), bureaucracy assistant, observability, health checks, auth + RBAC, tenant leak tests.
- Human-in-the-loop agents, pre-configured pipelines, English docs first, MIT license, invite-only contributions.
- Targets: MVP planning date 2027-02-28 (the date moves before the scope does). The v1 date is set after the MVP.

## Architecture (docs/architecture.md, ADRs in docs/adr/)
- ADR-0014 (accepted): PostgreSQL is a hardcoded integration (`PostgreSQLStore`, `src/plugins/relational_db/postgres.py`). The plugin system (ADR-0001) is deprecated and each backend becomes a direct integration.
- ADR-0013 (accepted): auth with streamlit-authenticator, bcrypt, signed cookie. RBAC: `admin` manages data, `user` is read-only (`src/core/security/`).
- Planned stores: Qdrant (vectors), Neo4j AuraDB Free (graph), local rerank model, OpenAI-compatible LLM per agent, dedicated embedding provider.
- Multi-tenancy: shared documents, per-tenant data isolated by `tenant_id` and PostgreSQL RLS (ADR-0003).
- Celery + Redis, failed tasks persisted in DB, user re-runs from UI (ADR-0006). Observability: structlog + OTel to Grafana Alloy (ADR-0005).
- ADRs 0002-0012 are still `proposed`. ADR-0001 is superseded.

## Current state (as of 2026-11-27)
Built: PostgreSQL store (CRUD, ILIKE search), RBAC helpers and tenant helpers in `src/core/security/`, login UI (`src/ui/components/auth.py`: login form, logout, Redis login throttle, `require_auth`, `require_admin`, signed cookie checked against `users.session_version`), `legal_document.status` and a reject audit table, fetch agent (`src/agents/fetch/`: Sejm ELI, MinIO, REST API and Tavily strategies, pdf/docx/text/image formats, Mistral OCR) with its Celery task and Streamlit page (the page queues the task with no tenant, so every UI fetch saves shared rows), admin users page (`src/ui/pages/users.py`: create and deactivate users), Celery app, Streamlit app shell, settings (plain class: Qdrant, OTel, `min_confidence` and local rerank model keys, Cohere keys removed), LLM client (`src/core/llm/`, design record `llm-client`: `LLMClient.chat(agent_name, messages)` behind the `ChatModel` port, per-agent `LLM_<FIELD>_<AGENT>` with fallback to `LLM_<FIELD>`, seven agents in `LLM_AGENTS`, each httpx phase gets timeout / 4, 1 MiB reply cap, a key needs https unless the host is loopback, error messages never hold the key, content or base URL; no agent calls it yet), Alembic migrations, Docker stack, CI.
Verified gaps (2026-11-20): no RLS on `legal_document` (RLS policies exist only on `tenants` and `users`), no full-text search.
Tenant guard in `PostgreSQLStore` (2026-11-18, design records `tenant-write-guard` and `tenant-read-guard`): the tenant comes from the argument, else `get_current_tenant()`. Reads return own rows and shared (`NULL` tenant) rows. A caller with no tenant reads only shared rows. Writes and `delete_document` match the tenant strictly (`IS NOT DISTINCT FROM`). A foreign row behaves as a missing row.
Open tenant gaps: no RLS on `legal_document` (the store filter is the only isolation), a caller with no tenant can delete every shared row (only RBAC guards it), no index on `legal_document.tenant_id`, `get_recent_changes` has no `LIMIT`, and the RLS session hook sets the tenant from the context, not from the resolved argument. The RLS policies on `tenants` and `users` match only the current tenant, and an empty setting matches nothing. A `legal_document` policy needs more: `app.current_tenant` must equal the tenant that `save_document` writes, also when the fetch task passes the tenant as an argument and the context has none. It must also keep the shared-read and strict tenant-write rules above, and let the admin `PostgreSQLStore.reject` delete across tenants (review state is global). Do this with a `SECURITY DEFINER` function, as for `public.auth_lookup_user`, never with an admin flag read from a setting, because any app code path can set a setting. Strict tenant-write with an empty setting still lets a caller with no tenant write and delete shared rows, so RLS alone does not close that gap.
Not built: other agents (only `src/agents/fetch/` exists), Qdrant, Neo4j, embeddings, search, observability (`src/core/observability/` is an empty package), health checks, most UI pages.
Open LLM client limits (design record `llm-client`, `review.md`): a server that sends headers one byte at a time can exceed the 1.25 x timeout bound (a hard bound needs a thread or async cancel), the client opens a new httpx connection for each call, and a traceback keeps the `chat` frame, whose locals hold the key, base URL and messages (a logger that captures traceback locals can expose them).

## Work hierarchy
ADR > milestone > issue > branch > PR. An ADR records a decision. A milestone groups the issues that deliver it. An issue is one task. A branch is named after its issue. A PR closes the issue (`Closes #N`). Status, phase, priority and size live on the board (Project 5).
Do not write issue or PR numbers in docs, code comments or this file.
The only planning layer in the repo is the design record of a task, in `docs/design/<slug>/` (requirements, design paths, decision, tasks, specs, QA cases and results). Commit it with the task. The slug names the topic and has no issue number (for example `worker-store-close`). Older slugs keep their names. Do not add other planning layers (plan files, ticket files, custom ids).
The MVP planning date is 2027-02-28. Rerank is local (Cohere dropped), and an eval picks the model.

## Known drift (verify before work)
- Older plugin-era issues (protocols, PluginManager, Memgraph) describe a design that ADR-0014 and the charter replaced. Check each one with the owner before work.
- Issues use "Todo" only on the board. No issue is marked In Progress.

## Working rules for this repo
- Git remote operations (clone, push, `gh`) go through the `git-agent` subagent. A hook blocks `.env` access and pipes in Bash.
- Design gate for an issue that crosses a module boundary: the issue has a "Contract" section (inputs, outputs and errors of each call, checked against the validation of the callee). The `solution-architect` agent reviews the interface before any code. When the issue is picked, the architect reads it again against the current code and updates the issue text before the branch is created.
- When the owner changes a decision at the design gate, update the issue text in the same step. CodeRabbit checks the PR against the linked issue.
- CodeRabbit does not review this repo automatically. Post `@coderabbitai review` on each new PR.
- Merge only after every check is complete. `integration-test` is not a required check, so `gh pr merge --auto` can merge before it ends.
- Each Celery task has at least one integration test with production collaborators. Mock only the network edge.
- Quality gate before a task is done: ruff check, ruff format --check, pyright, pytest.
- Coverage commands and gates: see the "Coverage and mutation gates" section of CONTRIBUTING.md.
- Mutation testing (blocking in CI via scripts/mutation_score.py, runs in CI only, not in pre-commit): see the same CONTRIBUTING.md section.
