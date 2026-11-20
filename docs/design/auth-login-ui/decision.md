# Decision: auth-login-ui

## Context
The login adapter, RBAC wiring and most login tests are merged. The open gaps are: no unit tests for `rbac.py`, no UI tests that prove a demoted or deactivated admin loses admin pages, stale ADR-0004 text, and `jwt` used as a transitive dependency only. See requirements.md.

## Options
- Path 1: additive hardening. Tests, text scrub and a pyjwt pin. No production change.
- Path 2: single enforcement point. UI `require_admin` calls core `check_privilege_escalation`. Removes `require_role` and `InvalidRoleError` from the public API.

## Decision
Path 1, chosen by the owner at G1. Two reviewer changes apply:
- Add a fail-open test for `principal.require_admin_principal` (`principal.py`), which is a third admin check.
- Each demotion or deactivation test runs `require_auth()` with a stubbed login lookup that returns the changed row, then `require_admin()`. A test that edits only `st.session_state["user"]` proves nothing.

## Consequences
- No runtime behaviour changes. The public API is unchanged.
- `require_role` and `InvalidRoleError` stay as dead code, covered only by tests. Removing them is a separate follow-up issue that needs owner approval.
- The pyjwt pin must resolve against streamlit-authenticator 0.4.2 and pass `pip-audit`. If it does not, stop and report.
- Review includes one manual mutation per guard (guard removed, test fails).
