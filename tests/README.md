# Tests

The test suite is organised by **scope**, not by component prefix.

```
tests/
├── conftest.py      # global pytest config + pytest_plugins
├── fixtures/        # shared pytest fixtures (auto-loaded)
├── factories/       # fake classes + make_* builders (imported by tests)
├── unit/            # pure unit tests — no external services
│   ├── config/
│   ├── plugins/
│   └── ...
├── integration/     # postgres/redis-backed tests (marked `integration`)
├── e2e/             # whole-stack tests
└── README.md
```

- `unit/` mirrors `src/` one level deep (`config/`, `plugins/`, …) and runs
  in CI's default unit job with no external services.
- `factories/` holds fake plugin classes (importable under the `fake_plugins`
  module name, see `fixtures/plugins.py`) plus `make_*` factory functions.
- `fixtures/` holds shared pytest fixtures; `tests/conftest.py` loads them via
  `pytest_plugins`.
- Tests needing live PostgreSQL/Redis are marked `integration`; whole-stack
  flows belong in `e2e/`. Both are excluded from the default unit run.
- Security tests (auth, RBAC, cross-tenant leak, ADR-0003/ADR-0004) are
  marked `security`.

Run the unit suite with `uv run pytest -m "not integration"`.
