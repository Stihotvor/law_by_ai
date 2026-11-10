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

- Python 3.13+
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

- The suite is organised by scope: `tests/unit/` (no external services),
  `tests/integration/` (live PostgreSQL/Redis), `tests/e2e/` (whole stack).
- Shared fixtures live in `tests/fixtures/` (loaded via `pytest_plugins`);
  fake classes and `make_*` builders live in `tests/factories/`.
- Security tests (auth, RBAC, multi-tenant leak tests) are marked `security`.
- Tests requiring external services (PostgreSQL, Qdrant, Memgraph, Redis) are
  marked `integration` and are excluded from default runs.

### Coverage and mutation gates

The gate agent reads its checks from `.claude/quality-gates.json` (lint, format, types, security, tests, lock, audit); run the gate with `--with-network`, because a skipped audit check counts as not run.

```bash
PYTHONPATH=src uv run pytest -m "not integration" --cov --cov-branch --cov-report=xml --cov-report=term-missing
uv run diff-cover coverage.xml --compare-branch=origin/main --fail-under=90
uv run coverage report --include='src/agents/*' --fail-under=100
uv run mutmut run && uv run mutmut results
uv run python scripts/mutation_score.py
```

- Repo-wide branch coverage must stay at or above `fail_under` in `pyproject.toml`
  (88%; raise it as coverage grows, never lower it).
- `src/agents` has its own floor of 100% (CI runs `coverage report --include='src/agents/*' --fail-under=100`).
- New and changed lines need at least 90% coverage (`diff-cover`, pull requests only).
- Mutation testing (`mutmut`) is scoped by `[tool.mutmut]` in `pyproject.toml` to
  `src/agents/fetch` with tests in `tests/unit/agents/fetch`. The CI job is
  blocking: after the run, `scripts/mutation_score.py` fails it when the killed
  percentage is below `MIN_KILLED_PERCENT` (the one place the threshold lives; raise
  it as the score grows, never lower it). The job runs in CI only and uploads a
  results summary. To change the
  scope, edit `source_paths` and `pytest_add_cli_args_test_selection` in
  `pyproject.toml` (mutmut 3.8.1 reads its scope only from that file). The CI
  job fails (it does not skip) when `src/agents/fetch` does not exist.
- Each Celery task has at least one integration test with production
  collaborators. Mock only the network edge.

## Design gate for cross-module issues

An issue crosses a module boundary when its code in one module calls another
module, in the same package or in another package.

1. Write a "Contract" section in the issue. For each call, list the inputs,
   the outputs and the errors. Check each input against the validation of the
   callee.
2. Get a review of the interface from the architect (the `solution-architect`
   agent) before any code.
3. When you pick the issue, the architect reads it again against the current
   code and updates the issue text. Then create the branch.

## Branching & PRs

- Use a `feature/`, `fix/`, or `docs/` branch named after the issue
  (e.g., `docs/revised-architecture-plan`).
- A new ADR goes in its own PR on an `adr/` branch (e.g., `adr/local-reranker`). The PR title starts with `ADR: ` (e.g., `ADR: use a local reranker`).
- Reference the issue in the PR body: `Closes #N` or `Refs #N`.
- CI runs two workflows on every PR: `ci` (lint, typecheck, security, unit +
  integration tests, outside `docs/`) and `docs` (docs build, on `docs/`
  changes). The PR must be green before merging.

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
