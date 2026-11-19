# Path 2: Single enforcement point

Lens: `core/security` is the only place that decides allow or deny.

- UI `require_admin` calls `check_privilege_escalation(current_role(), ADMIN)`, catches `PrivilegeEscalationError`, warns and stops. `is_admin` leaves the UI import.
- Delete `require_role` and `InvalidRoleError` (no caller outside `rbac.py` and `__init__.py`). Update `__all__` and docstrings.
- Same tests, text scrub and pyjwt pin as path 1.
- `require_admin_principal` in `principal.py` stays a second, separate check.

Effort: S. Main risk: removes public names, which conflicts with "no public API change" in the requirements. It needs owner sign-off. Message text "operation" must not be pinned by a test the change breaks.
