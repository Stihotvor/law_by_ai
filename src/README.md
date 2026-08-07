# Source packages

All Python packages live under `src/` (src-layout). Package discovery in
`pyproject.toml` (`[tool.setuptools.packages.find] where = ["src"]`) maps these
onto the importable names `core`, `plugins`, `agents`, `tasks`, `ui`, `config`,
`data`, and `storage`.

Repo-root directories hold non-package concerns: `docker/` (build/deploy),
`docs/` (documentation), `evals/` (evaluations), `scripts/` (tooling),
`tests/` (test suites).
