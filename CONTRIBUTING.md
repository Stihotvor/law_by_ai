# Contributing to Law by AI

Thanks for your interest in contributing! This project is currently
**invite-only** and in early implementation. Before contributing, read the
[Intention doc](docs/intention.md) and the [Architecture doc](docs/architecture.md)
to understand the scope and design constraints.

## Code of conduct

Be respectful and constructive. This is a community tool meant to protect
citizens' rights — keep the focus on the mission.

## Getting started

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) installed **globally** (standalone), e.g.:
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
  uv is **not a project dependency** — never `pip install uv` into the project
  venv. It manages `.venv` for you.

### Setup

```bash
uv sync --extra dev --extra docs
```

### Running checks

All checks must pass before opening a PR:

```bash
uv run ruff check .                 # lint
uv run ruff format --check .        # format
uv run pytest                       # tests
uv run mkdocs build --strict -f docs/mkdocs.yml  # docs build
```

Run `uv run ruff format .` and `uv run ruff check . --fix` to auto-fix
formatting and lint issues.

## Testing

- Unit tests live in `tests/test_plugins/`, `tests/test_agents/`,
  `tests/test_tasks/`.
- Security tests (auth, RBAC, multi-tenant leak tests) live in
  `tests/test_security/` and are marked `security`.
- Tests requiring external services (PostgreSQL, Qdrant, Memgraph, Redis) are
  marked `integration` and are excluded from default runs.

## Branching & PRs

- Use a `feature/`, `fix/`, or `docs/` branch named after the issue
  (e.g., `docs/revised-architecture-plan`).
- Reference the issue in the PR body: `Closes #N` or `Refs #N`.
- CI runs two workflows on every PR: `ci` (lint + tests, outside `docs/`) and
  `docs` (docs build, on `docs/` changes). The PR must be green before merging.

## Architecture decisions

Significant decisions are tracked as [ADRs](docs/adr/index.md). If your change
has architectural impact, add or update an ADR.

## License

By contributing you agree that your contributions are licensed under the
[MIT License](LICENSE).
