"""RBAC layer (ADR-0004).

Role constants and a ``require_role`` decorator / predicate usable from
both the core security module and the Streamlit adapter.

Design decisions:
- Roles are plain strings: ``"admin"`` and ``"user"``.
- ``require_role()`` is a *predicate* — it returns a callable that
  accepts a ``role`` argument and returns ``True`` / ``False``.
  This avoids coupling to any particular framework's request cycle.
- ``is_admin()`` and ``is_user()`` are convenience helpers.
- Privilege-escalation guard: a ``user``-scoped function that receives an
  ``admin``-level operation must raise ``PermissionError`` (or a subclass)
  rather than silently succeeding.
"""

from __future__ import annotations

from collections.abc import Callable

# ---------------------------------------------------------------------------
# Role constants — importable as ``from core.security import ADMIN, USER``
# ---------------------------------------------------------------------------

ADMIN = "admin"
USER = "user"

VALID_ROLES = {ADMIN, USER}

# ---------------------------------------------------------------------------
# Convenience predicates
# ---------------------------------------------------------------------------


def is_admin(role: str) -> bool:
    """Return True if *role* is ``ADMIN``."""
    return role == ADMIN


def is_user(role: str) -> bool:
    """Return True if *role* is ``USER``."""
    return role == USER


def valid_role(role: str) -> bool:
    """Return True if *role* is a known role."""
    return role in VALID_ROLES


# ---------------------------------------------------------------------------
# Privilege-escalation guard
# ---------------------------------------------------------------------------


class InvalidRoleError(ValueError):
    """Raised when a role is not valid (not ADMIN or USER)."""

    def __init__(self, role: str) -> None:
        self.role = role
        super().__init__(f"Invalid role: {role!r}")


class PrivilegeEscalationError(PermissionError):
    """Raised when a ``user`` attempts an ``admin``-scoped operation."""

    def __init__(self, operation: str, requested_role: str, required_role: str) -> None:
        self.operation = operation
        self.requested_role = requested_role
        self.required_role = required_role
        super().__init__(
            f"Privilege escalation denied: user with role "
            f"'{requested_role}' cannot perform '{operation}' — "
            f"required role: '{required_role}'"
        )


def check_privilege_escalation(
    role: str,
    required_role: str = ADMIN,
) -> None:
    """Raise ``PrivilegeEscalationError`` if *role* does not meet *required_role*.

    Usage (in a service function):

    ````python
    from core.security import check_privilege_escalation

    def delete_document(document_id: str, role: str) -> None:
        check_privilege_escalation(role, required_role=ADMIN)
        # ... proceed — only admin can reach here
    ````
    """
    if role not in VALID_ROLES:
        raise PrivilegeEscalationError(
            operation="unknown operation",
            requested_role=role,
            required_role=required_role,
        )
    if role != required_role:
        raise PrivilegeEscalationError(
            operation="operation",
            requested_role=role,
            required_role=required_role,
        )


# ---------------------------------------------------------------------------
# ``require_role`` — decorator / predicate factory
# ---------------------------------------------------------------------------


def require_role(
    required: str = ADMIN,
) -> Callable[[str], bool]:
    """Factory that returns a ``callable[[role], bool]``.

    The returned callable can be used as a predicate in any context
    (CLI, Celery, Streamlit, FastAPI, tests). The check is a plain equality
    comparison, so custom (non-``VALID_ROLES``) requirements work too.

    Example::

        from core.security import require_role

        # Streamlit page guard:
        # if not require_role(ADMIN)(st.session_state.user["role"]):
        #     st.error("Admin required"); st.stop()

        # Celery task guard:
        # if not require_role(ADMIN)(worker_role):
        #     raise PrivilegeEscalationError(...)

        # Test assertion:
        # assert require_role(ADMIN)(user_role)
    """

    def _check(role: str) -> bool:
        return role == required

    return _check
