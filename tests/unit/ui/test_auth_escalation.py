"""Privilege escalation in an open session: demotion, deactivation and the admin guard.

Each demotion or deactivation test runs ``require_auth()`` with ``_lookup`` stubbed to
return the changed row, then ``require_admin()``. The Streamlit module inside
``ui.components.auth`` is a MagicMock whose ``stop`` raises a sentinel exception.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from factories.auth import SESSION_VERSION, Stopped, login_row

from core.security.principal import RequestPrincipal, get_principal
from ui.components import auth

ADMIN_EMAIL = "admin@x.com"
VERSION = SESSION_VERSION
ADMIN_REQUIRED = "Admin role required."
_MISSING = object()


@dataclass
class Lookup:
    """Stub for ``auth._lookup``: returns ``row`` and records each email."""

    row: dict[str, Any] | None
    calls: list[str] = field(default_factory=list)

    def __call__(self, email: str) -> dict[str, Any] | None:
        self.calls.append(email)
        return self.row


@dataclass
class Env:
    st: MagicMock
    lookup: Lookup
    login_form: MagicMock


@pytest.fixture
def env(fake_st: MagicMock) -> Iterator[Env]:
    """Open admin session: a valid "<email>|<version>" claim with a future expiry."""
    fake_st.session_state.update(
        {
            auth.USERNAME_KEY: f"{ADMIN_EMAIL}|{VERSION}",
            auth.EXPIRES_KEY: time.time() + 3600,
            auth.LOGOUT_KEY: False,
        }
    )
    lookup = Lookup(login_row())
    with (
        patch.object(auth, "get_settings", MagicMock()),
        patch.object(auth, "CookieModel", MagicMock()),
        patch.object(auth, "_lookup", lookup),
        patch.object(auth, "_cookie_sent", lambda name: False),
        patch.object(auth, "logout_button"),
        patch.object(auth, "login_form") as login_form,
    ):
        yield Env(fake_st, lookup, login_form)


def _admin_page() -> dict[str, Any]:
    """One rerun of an admin page: require_auth() then require_admin()."""
    user = auth.require_auth()
    auth.require_admin()
    return user


def _open_admin_session(env: Env) -> None:
    """First rerun: the lookup returns the admin row and the admin guard passes."""
    assert _admin_page()["role"] == "admin"
    env.st.warning.assert_not_called()
    env.st.stop.assert_not_called()


# --- demotion and deactivation in an open session -------------------------------


def test_demoted_admin_loses_admin_page(env: Env) -> None:
    _open_admin_session(env)
    assert get_principal() == RequestPrincipal(email=ADMIN_EMAIL, role="admin")
    env.lookup.row = login_row(role="user")
    with pytest.raises(Stopped):
        _admin_page()
    assert env.lookup.calls == [ADMIN_EMAIL, ADMIN_EMAIL]
    assert env.st.session_state[auth.SESSION_USER_KEY]["role"] == "user"
    assert get_principal() == RequestPrincipal(email=ADMIN_EMAIL, role="user")
    env.st.warning.assert_called_once_with(ADMIN_REQUIRED)
    env.st.stop.assert_called_once()


def test_stale_admin_session_role_is_replaced_by_database_role(env: Env) -> None:
    env.st.session_state[auth.SESSION_USER_KEY] = login_row(role="admin")
    env.lookup.row = login_row(role="user")
    assert auth.require_auth()["role"] == "user"
    assert env.st.session_state[auth.SESSION_USER_KEY]["role"] == "user"
    with pytest.raises(Stopped):
        auth.require_admin()
    env.st.warning.assert_called_once_with(ADMIN_REQUIRED)
    env.st.stop.assert_called_once()


def test_deactivated_admin_is_signed_out_before_admin_code(env: Env) -> None:
    _open_admin_session(env)
    env.lookup.row = login_row(is_active=False)
    with pytest.raises(Stopped):
        auth.require_auth()  # stops here, so the page never reaches require_admin()
    assert env.lookup.calls == [ADMIN_EMAIL, ADMIN_EMAIL]
    assert auth.SESSION_USER_KEY not in env.st.session_state
    assert auth.USERNAME_KEY not in env.st.session_state
    assert auth.current_role() == ""
    assert get_principal() is None
    env.login_form.assert_called_once()
    env.st.stop.assert_called_once()


def test_deactivated_admin_has_no_admin_access_on_next_rerun(env: Env) -> None:
    _open_admin_session(env)
    env.lookup.row = login_row(is_active=False)
    with pytest.raises(Stopped):
        _admin_page()
    with pytest.raises(Stopped):
        auth.require_admin()
    env.st.warning.assert_called_once_with(ADMIN_REQUIRED)


# --- admin guard ----------------------------------------------------------------------


def test_user_on_admin_page_is_stopped(env: Env) -> None:
    env.lookup.row = login_row(role="user")
    with pytest.raises(Stopped):
        _admin_page()
    assert env.st.session_state[auth.SESSION_USER_KEY]["role"] == "user"
    env.st.warning.assert_called_once_with(ADMIN_REQUIRED)
    env.st.stop.assert_called_once()


@pytest.mark.parametrize(
    "user",
    [_MISSING, None, "admin", ["admin"], {}, {"role": None}, {"role": 1}, {"role": ["admin"]}],
    ids=["missing", "none", "str", "list", "no-role", "none-role", "int-role", "list-role"],
)
def test_current_role_fails_closed(fake_st: MagicMock, user: object) -> None:
    if user is not _MISSING:
        fake_st.session_state[auth.SESSION_USER_KEY] = user
    assert auth.current_role() == ""
    with pytest.raises(Stopped):
        auth.require_admin()
    fake_st.warning.assert_called_once_with(ADMIN_REQUIRED)


def test_current_role_keeps_upper_case_and_admin_guard_stops(fake_st: MagicMock) -> None:
    fake_st.session_state[auth.SESSION_USER_KEY] = {"role": "ADMIN"}
    assert auth.current_role() == "ADMIN"
    with pytest.raises(Stopped):
        auth.require_admin()
    fake_st.warning.assert_called_once_with(ADMIN_REQUIRED)


def test_current_role_returns_admin_and_admin_guard_passes(fake_st: MagicMock) -> None:
    fake_st.session_state[auth.SESSION_USER_KEY] = {"role": "admin"}
    assert auth.current_role() == "admin"
    auth.require_admin()
    fake_st.warning.assert_not_called()
    fake_st.stop.assert_not_called()
