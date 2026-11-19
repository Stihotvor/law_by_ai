# Path 1: Additive hardening

Lens: change no production behaviour.

- Add `tests/unit/core/security/test_rbac.py` for every public name in `rbac.py` (100% line coverage).
- Add 3+ UI escalation tests to `tests/unit/test_ui_auth.py`: demoted admin, deactivated admin, `user` on an admin page (DB-backed login).
- Scrub ADR-0004 and `token_store` text (docstrings, comments, READMEs).
- Add `pyjwt==<resolved>` to `pyproject.toml`.
- Keep `require_role`, `InvalidRoleError` and `check_privilege_escalation` as they are. `require_role` and `InvalidRoleError` stay dead code, covered only by tests.
- Two deciders remain: UI `is_admin` and core `check_privilege_escalation`.

Effort: S. Main risk: pyjwt pin conflict or pip-audit hit. A demoted-admin test can pass without the guard, so verify by mutation.
