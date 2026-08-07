# Tests

Test suites grouped by concern.

- `test_plugins/` — plugin protocol/implementation tests
- `test_agents/` — agent behavior tests
- `test_tasks/` — Celery task tests
- `test_security/` — auth, RBAC, and cross-tenant leak tests (ADR-0003, ADR-0004)

Integration tests are marked `integration` and excluded from CI's default run.
