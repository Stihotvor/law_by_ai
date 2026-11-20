"""Role predicates and the privilege escalation check in core.security.rbac."""

import pytest

from core.security.rbac import (
    ADMIN,
    USER,
    VALID_ROLES,
    InvalidRoleError,
    PrivilegeEscalationError,
    check_privilege_escalation,
    is_admin,
    is_user,
    require_role,
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
def test_unknown_role_raises_privilege_escalation_not_invalid_role(role: str) -> None:
    with pytest.raises(PrivilegeEscalationError) as exc_info:
        check_privilege_escalation(role)
    err = exc_info.value
    assert not isinstance(err, InvalidRoleError)
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


def test_invalid_role_error_carries_role() -> None:
    err = InvalidRoleError("x")
    assert isinstance(err, ValueError)
    assert err.role == "x"
    assert repr("x") in str(err)


def test_require_role_default_is_admin_only() -> None:
    check = require_role()
    assert check("admin") is True
    assert check("user") is False
    assert check("") is False
    assert check("root") is False


def test_require_role_custom_required() -> None:
    check = require_role("user")
    assert check("user") is True
    assert check("admin") is False
    assert check("") is False
    assert check("root") is False


def test_require_role_nonstandard_required_returns_false() -> None:
    check = require_role("root")
    assert check("admin") is False
    assert check("root") is True
