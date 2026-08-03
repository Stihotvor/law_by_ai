# Contributing to Law by AI

Thanks for your interest in contributing! This project is currently
**invite-only** and in early implementation. Before contributing, read the
[Intention doc](docs/intention.md) and the [Architecture doc](docs/architecture.md)
to understand the scope and design constraints.

## Code of conduct

Be respectful and constructive. This is a community tool meant to protect
citizens' rights — keep the focus on the mission. All participants must follow
the [Code of Conduct](CODE_OF_CONDUCT.md).

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

## Contribution model

The governance model is defined in [ADR-0012](docs/adr/0012-license-contribution-model.md).
In short:

- **License**: the project is released under the [MIT License](LICENSE).
- **Access**: contributions are **invite-only** during the early
  implementation phase. The project will open to public contributions once v1
  is stable, at the maintainer's discretion.
- **DCO**: every commit must include a `Signed-off-by` trailer certifying the
  [Developer Certificate of Origin](DCO). There is no separate CLA:
  ```bash
  git commit -s -m "feat: ..."
  ```
  A commit is compliant when it has a line like
  `Signed-off-by: Your Name <you@example.com>` at the end of the message.
- **License grant**: by contributing you agree that your contributions are
  licensed under the MIT License.
- **Process**: branches named after the issue (`feature/`, `fix/`, `docs/`),
  PRs reference the issue (`Closes #N` / `Refs #N`), and all checks must pass
  (see below).

## License

The project is licensed under the [MIT License](LICENSE). By contributing you
agree that your contributions are licensed under the MIT License and that you
certify the [Developer Certificate of Origin](DCO) via a `Signed-off-by`
trailer on each commit.
