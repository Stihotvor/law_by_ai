"""Core security module (ADR-0003, ADR-0013).

Authentication (ADR-0013): login/session management is delegated to
``streamlit-authenticator`` (see ``ui/components/auth.py``); this package only
keeps the framework-agnostic pieces:

Passwords:
    - hash_password(), check_password()  — bcrypt helpers

Authorization (RBAC):
    - ADMIN, USER
    - is_admin(), is_user(), valid_role()
    - check_privilege_escalation(), PrivilegeEscalationError
    - require_role()

Tenancy:
    - set_current_tenant(), get_current_tenant(), reset_current_tenant()
    - tenant_context(), without_tenant()
    - export_current_tenant()
"""

from .passwords import check_password, hash_password
from .rbac import (
    ADMIN,
    USER,
    InvalidRoleError,
    PrivilegeEscalationError,
    check_privilege_escalation,
    is_admin,
    is_user,
    require_role,
    valid_role,
)
from .tenant import (
    export_current_tenant,
    get_current_tenant,
    reset_current_tenant,
    set_current_tenant,
    tenant_context,
    without_tenant,
)

__all__ = [
    "ADMIN",
    "USER",
    "InvalidRoleError",
    "PrivilegeEscalationError",
    "check_password",
    "check_privilege_escalation",
    "export_current_tenant",
    "get_current_tenant",
    "hash_password",
    "is_admin",
    "is_user",
    "require_role",
    "reset_current_tenant",
    "set_current_tenant",
    "tenant_context",
    "valid_role",
    "without_tenant",
]
