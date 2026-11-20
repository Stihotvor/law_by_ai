"""Auth layer sets the request principal on every rerun and clears it on sign-out.

The Streamlit module inside ``ui.components.auth`` is a MagicMock, so each
function runs in the test thread and the principal context var is visible here.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from factories.auth import Stopped

from core.security.principal import (
    PrincipalRequiredError,
    RequestPrincipal,
    get_principal,
    require_admin_principal,
    set_principal,
)
from ui.components import auth

ADMIN_USER = {
    "id": "u-1",
    "tenant_id": "t-1",
    "email": "a@x.pl",
    "name": "Admin",
    "role": "admin",
}


def test_require_auth_sets_the_principal(fake_st: MagicMock) -> None:
    user: dict[str, Any] = dict(ADMIN_USER)
    with (
        patch.object(auth, "get_settings", MagicMock()),
        patch.object(auth, "CookieModel", MagicMock()),
        patch.object(auth, "_session_user", lambda cookie: user),
        patch.object(auth, "logout_button"),
    ):
        assert auth.require_auth() == user
    assert get_principal() == RequestPrincipal("a@x.pl", "admin")


def test_failed_login_sets_no_principal(fake_st: MagicMock) -> None:
    fake_st.form_submit_button.return_value = True
    with (
        patch.object(auth, "get_settings", MagicMock()),
        patch.object(auth, "CookieModel", MagicMock()),
        patch.object(auth, "_session_user", lambda cookie: None),
        patch.object(auth, "_cookie_sent", lambda name: False),
        patch.object(auth, "_attempt", lambda email, password: None),
        pytest.raises(Stopped),
    ):
        auth.require_auth()
    fake_st.error.assert_called_once_with(auth._LOGIN_FAILED)
    assert get_principal() is None
    with pytest.raises(PrincipalRequiredError):
        require_admin_principal()


def test_sign_out_clears_the_principal(fake_st: MagicMock) -> None:
    set_principal(RequestPrincipal("a@x.pl", "admin"))
    fake_st.session_state[auth.LOGOUT_KEY] = False
    with (
        patch.object(auth, "_cookie_sent", lambda name: False),
        patch.object(auth, "login_form"),
        pytest.raises(Stopped),
    ):
        auth._sign_out(MagicMock(), "cookie")
    fake_st.stop.assert_called_once()
    assert get_principal() is None


def test_logout_button_clears_the_principal_before_rerun(fake_st: MagicMock) -> None:
    set_principal(RequestPrincipal("a@x.pl", "admin"))
    fake_st.session_state[auth.SESSION_USER_KEY] = dict(ADMIN_USER)
    fake_st.sidebar.button.return_value = True
    seen: list[RequestPrincipal | None] = []
    fake_st.rerun.side_effect = lambda: seen.append(get_principal())
    with patch.object(auth, "_revoke", lambda user: True):
        auth.logout_button(MagicMock())
    assert seen == [None]
