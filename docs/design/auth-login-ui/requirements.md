# Requirements: auth-login-ui

The login adapter, the RBAC wiring, login throttling and most login tests are already merged. This task closes the verified gaps only. The admin UI to create and deactivate users is out of scope.

## Business Goals
- Maintainers get proof that a `user` cannot act as an `admin`. The MVP needs auth, RBAC and privilege-escalation tests.
- Decided: add tests and remove drift. Add no new feature.
- Test: every rule in `src/core/security/rbac.py` has a unit test that fails when the rule is removed.

## Technical Constraints
- Stack: Python 3.13, streamlit 1.66.1, streamlit-authenticator 0.4.2 (ADR-0013), pytest. Quality gate: ruff check, ruff format --check, pyright, pytest.
- `src/ui/components/auth.py` imports `jwt` to catch `jwt.PyJWTError`. PyJWT is only a transitive dependency of streamlit-authenticator.
- Decided: keep the import, because `CookieModel.get_cookie` raises that error. Declare `pyjwt` as a direct, exactly pinned dependency in `pyproject.toml`, like the other pins.
- Decided: remove the stale ADR-0004 mentions in `src/core/security/` and the READMEs that describe it. ADR-0004 is superseded. Keep the RBAC rules of ADR-0004, and cite ADR-0013 and ADR-0003.
- No change to the public API, the database schema or the settings.
- Not in scope: DB-level RLS on `legal_document`.

## Edge Cases
- A role string that is empty, `None`-like, upper case (`"ADMIN"`) or unknown must fail closed in `rbac.py` and in `current_role()`.
- An admin demoted to `user`, or deactivated, in the database while the session is open loses admin pages on the next rerun.
- A cookie signed with the right key that claims a higher role still gives the database role. This is already tested. Keep it.
- `check_privilege_escalation` with an unknown role raises `PrivilegeEscalationError`, not `InvalidRoleError`. Pin the present behaviour with a test.

## Failure Modes
- A denied action raises `PrivilegeEscalationError` (a `PermissionError`) in core code. In the UI it shows "Admin role required." and stops the page. No data change happens.
- A test must fail when `require_admin`, `is_admin` or `check_privilege_escalation` fail open.
- If the jwt dependency pin conflicts with streamlit-authenticator, `uv pip install -e ".[dev]"` fails. The task is not done until it resolves and `pip-audit` passes.

## Success Metrics
- A new `tests/unit/core/security/test_rbac.py` covers every public name in `rbac.py`, and its line coverage of `rbac.py` is 100%.
- At least 3 new privilege-escalation tests in the UI layer: demoted admin, deactivated admin, `user` calling an admin-only page. Each fails when the guard is removed (checked by one manual mutation in review).
- 0 matches for `ADR-0004` and `token_store` in `src/core/security/`. The remaining mentions in `src/*/README.md` are replaced or removed.
- `pyjwt` is listed in `pyproject.toml` with an exact pin. `ruff`, `pyright`, `pytest -m "not integration"` and `pip-audit` all pass. The CI mutation gate does not drop.
