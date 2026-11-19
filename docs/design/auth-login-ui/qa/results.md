# QA results: auth-login-ui

Run: `.venv/bin/pytest -m "not integration"`. No new QA-only test file: evidence cites the tests of T2 and T3.
Paths below are relative to /home/yevhend/claude-projects/law_by_ai.

| Case | Status | Evidence |
|---|---|---|
| QA-001 | pass | tests/unit/core/security/test_rbac.py:43 test_admin_passes_admin_check |
| QA-002 | pass | test_rbac.py:47 test_user_cannot_pass_admin_check |
| QA-003 | pass | test_rbac.py:28 (role "") |
| QA-004 | pass | test_rbac.py:69 test_none_role_fails_closed |
| QA-005 | pass | test_rbac.py:28 ("ADMIN") |
| QA-006 | pass | test_rbac.py:28 and :55 ("root"; "superuser" is the same non-member path) |
| QA-007 | pass | test_rbac.py:57 |
| QA-008 | pass | test_rbac.py:47 |
| QA-009 | pass | test_rbac.py:43 |
| QA-010 | pass | test_rbac.py:77 test_user_denied_on_repeated_admin_checks |
| QA-011 | pass | test_rbac.py:92 test_require_role_custom_required. The case text was corrected: require_role returns False and never raises (spec T2). |
| QA-012 | pass | test_rbac.py:92 test_require_role_custom_required |
| QA-013 | not-automated | Needs mutating product code and re-running the suite (mutation check). |
| QA-014 | pass | test_rbac.py covers every public name. Main session measured --cov=core.security.rbac: 100% (30 statements, 4 branches). |
| QA-015 | pass | tests/unit/ui/test_auth_escalation.py:124 test_demoted_admin_loses_admin_page |
| QA-016 | pass | test_auth_escalation.py:135 and :149 |
| QA-017 | pass | test_auth_escalation.py:162 test_user_on_admin_page_is_stopped |
| QA-018 | pass | tests/unit/ui/test_auth_escalation.py:162 test_user_on_admin_page_is_stopped |
| QA-019 | pass | tests/unit/test_ui_auth.py:263 test_role_comes_only_from_database_row |
| QA-020 | partial | test_auth_escalation.py:176 and :185 cover malformed values and "ADMIN". Session role "" and "superuser" are not tested directly. |
| QA-021 | pass | test_auth_escalation.py:176 (missing, None); test_ui_auth.py:78 |
| QA-022 | pass | tests/unit/core/security/test_principal.py:81 (raises PrincipalRequiredError, a PermissionError; not PrivilegeEscalationError as the case text says) |
| QA-023 | pass | test_principal.py:93 and :118 |
| QA-024 | pass | test_principal.py:100 ("upper-admin") |
| QA-025 | not-automated | Needs removing the guard in a review branch and re-running. |
| QA-026 | pass | The named tests exist (demoted, deactivated, user_on_admin, current_role, require_admin_principal) and pass in the full run. |
| QA-027 | pass | `uv lock --check` passes; `grep -n 'pyjwt==' pyproject.toml` shows line 23. |
| QA-028 | not-automated | Checked by grep in the T4 done_when. No repo-content test, by design. |
| QA-029 | not-automated | Checked by grep in the T4 done_when. No repo-content test, by design. |
| QA-030 | not-automated | Checked by grep in the T4 done_when. No repo-content test, by design. |
| QA-031 | not-automated | Dev install needs network and installs packages. |
| QA-032 | not-automated | pip-audit needs network. |
| QA-033 | not-automated | Needs a conflicting pin and an install. |
| QA-034 | pass | ruff check, ruff format --check, pyright (0 errors), pytest -m "not integration" (1452 passed) and the Docker suite (1586 passed, 5 skipped before the last test edits). |
| QA-035 | not-automated | CI mutation score comparison. |
| QA-036 | not-automated | Diff review, not a test. |
