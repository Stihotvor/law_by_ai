"""authenticate: password check, inactive users and the dummy hash."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from factories.auth import (
    PLAIN,
    LoginEnv,
    login_row,
)

from core.security.passwords import DUMMY_HASH, check_password
from ui.components import auth


def test_authenticate_returns_public_fields_only(login_env: LoginEnv) -> None:
    user = auth.authenticate(" Admin@X.com ", PLAIN)
    assert user == {
        "id": "u-1",
        "tenant_id": "t-1",
        "email": "admin@x.com",
        "name": "Admin",
        "role": "admin",
    }


@pytest.mark.parametrize("change", [{"is_active": False}, {"role": "root"}])
def test_inactive_user_or_invalid_role_is_refused(
    login_env: LoginEnv, change: dict[str, Any]
) -> None:
    login_env.store.rows["admin@x.com"] = login_row(**change)
    assert auth.authenticate("admin@x.com", PLAIN) is None


def test_unknown_email_checks_dummy_hash(login_env: LoginEnv) -> None:
    with patch.object(auth, "check_password", wraps=check_password) as check:
        assert auth.authenticate("nobody@x.com", PLAIN) is None
    check.assert_called_once_with(PLAIN, DUMMY_HASH)
