"""Role predicates and the privilege escalation check in core.security.rbac."""

import pytest

from core.security.rbac import (
    ADMIN,
    USER,
    VALID_ROLES,
    PrivilegeEscalationError,
    check_privilege_escalation,
    is_admin,
    is_user,
    valid_role,
)

ODD_ROLES = ["", "ADMIN", "User", " admin", "root"]


def test_role_constants() -> None:
    assert ADMIN == "admin"
    assert USER == "user"
    assert {"admin", "user"} == VALID_ROLES


@pytest.mark.parametrize("role", ODD_ROLES)
def test_predicates_fail_closed_on_odd_roles(role: str) -> None:
    assert is_admin(role) is False
    assert is_user(role) is False
    assert valid_role(role) is False


def test_predicates_accept_exact_roles() -> None:
    assert is_admin("admin") is True
    assert is_user("user") is True
    assert is_admin("user") is False
    assert is_user("admin") is False
    assert valid_role("admin") is True
    assert valid_role("user") is True


def test_admin_passes_admin_check() -> None:
    assert check_privilege_escalation("admin") is None


def test_user_cannot_pass_admin_check() -> None:
    with pytest.raises(PrivilegeEscalationError) as exc_info:
        check_privilege_escalation("user")
    err = exc_info.value
    assert isinstance(err, PermissionError)
    assert err.operation == "operation"
    assert err.requested_role == "user"
    assert err.required_role == "admin"


@pytest.mark.parametrize("role", ODD_ROLES)
def test_unknown_role_raises_privilege_escalation(role: str) -> None:
    with pytest.raises(PrivilegeEscalationError) as exc_info:
        check_privilege_escalation(role)
    err = exc_info.value
    assert isinstance(err, PermissionError)
    assert err.operation == "unknown operation"
    assert err.requested_role == role
    assert err.required_role == "admin"


def test_none_role_fails_closed() -> None:
    assert is_admin(None) is False  # type: ignore[arg-type]
    assert is_user(None) is False  # type: ignore[arg-type]
    assert valid_role(None) is False  # type: ignore[arg-type]
    with pytest.raises(PrivilegeEscalationError):
        check_privilege_escalation(None)  # type: ignore[arg-type]


def test_user_denied_on_repeated_admin_checks() -> None:
    for _ in range(3):
        with pytest.raises(PrivilegeEscalationError):
            check_privilege_escalation("user")


def test_admin_fails_user_required_check() -> None:
    with pytest.raises(PrivilegeEscalationError) as exc_info:
        check_privilege_escalation("admin", required_role="user")
    err = exc_info.value
    assert err.requested_role == "admin"
    assert err.required_role == "user"
