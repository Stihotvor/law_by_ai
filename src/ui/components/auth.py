"""Streamlit auth adapter (ADR-0013): login, logout, signed cookie and the admin guard."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, NoReturn

import jwt
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError
from streamlit_authenticator.models import CookieModel

from config.settings import get_settings
from core.security.passwords import DUMMY_HASH, check_password
from core.security.rbac import is_admin, valid_role
from core.security.tenant import reset_current_tenant, set_current_tenant
from plugins.relational_db.postgres import PostgreSQLStore

# Session key that holds the signed-in user dict. Only login_form and require_auth
# write it, and only from the database row. Role and tenant never come from form
# fields, query params or the cookie: the cookie names only "<email>|<session_version>".
SESSION_USER_KEY = "user"
# Keys that CookieModel reads: the signed cookie value and the logout flag.
USERNAME_KEY = "username"
LOGOUT_KEY = "logout"
# Unix time when the session claim expires: the cookie expiry, applied to open sessions.
EXPIRES_KEY = "auth_expires"
_PUBLIC_FIELDS = ("id", "tenant_id", "email", "name", "role")
_LOGIN_FAILED = "Invalid email or password."


@st.cache_resource
def _store() -> PostgreSQLStore:
    return PostgreSQLStore()


def _cookie_sent(name: str) -> bool:
    """Return True when the browser sent the cookie with the page request."""
    return name in st.context.cookies


def _lookup(email: str) -> dict[str, Any] | None:
    """Return the login row; show "Login unavailable" and stop when the database is down."""
    try:
        return _store().get_login_user(email)
    except SQLAlchemyError:
        st.error("Login unavailable. Try again later.")
        st.stop()


def _usable(row: dict[str, Any]) -> bool:
    return bool(row["is_active"]) and valid_role(row["role"])


def _public(row: dict[str, Any]) -> dict[str, Any]:
    return {k: row[k] for k in _PUBLIC_FIELDS}


def _verify(email: str, password: str) -> dict[str, Any] | None:
    """Return the full login row when the password matches an active user with a valid role."""
    row = _lookup(email)
    if row is None:
        check_password(password, DUMMY_HASH)
        return None
    ok = check_password(password, row["password_hash"])
    return row if ok and _usable(row) else None


def authenticate(email: str, password: str) -> dict[str, Any] | None:
    """Return ``{id, tenant_id, email, name, role}`` for valid credentials, else None."""
    row = _verify(email, password)
    return _public(row) if row is not None else None


def login_form(cookie: CookieModel) -> None:
    """Show the login form; on success store the user, set the cookie and rerun."""
    with st.form("login"):
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password", key="login_password")
        submitted = st.form_submit_button("Log in")
    if not submitted:
        return
    row = _verify(email, password)
    if row is None:
        st.error(_LOGIN_FAILED)
        return
    st.session_state[SESSION_USER_KEY] = _public(row)
    st.session_state[USERNAME_KEY] = f"{row['email']}|{row['session_version']}"
    expiry = timedelta(days=get_settings().auth_cookie_expiry_days)
    st.session_state[EXPIRES_KEY] = (datetime.now() + expiry).timestamp()
    st.session_state[LOGOUT_KEY] = False
    cookie.set_cookie()
    st.rerun()


def _cookie_username(cookie: CookieModel) -> object:
    try:
        token = cookie.get_cookie()
    except jwt.PyJWTError:
        return None
    return token.get("username") if isinstance(token, dict) else None


def _claim(cookie: CookieModel) -> tuple[str, int] | None:
    """Return (email, session_version) from the session, else from the signed cookie.

    A session claim past its expiry returns None, so the caller signs out.
    """
    value = st.session_state.get(USERNAME_KEY)
    if value and st.session_state.get(EXPIRES_KEY, 0) <= datetime.now().timestamp():
        return None
    value = value or _cookie_username(cookie)
    if not isinstance(value, str) or "|" not in value:
        return None
    email, version = value.rsplit("|", 1)
    try:
        return email, int(version)
    except ValueError:
        return None


def _session_user(cookie: CookieModel) -> dict[str, Any] | None:
    claim = _claim(cookie)
    if claim is None:
        return None
    row = _lookup(claim[0])
    if row is None or not _usable(row) or row["session_version"] != claim[1]:
        return None
    return _public(row)


def _sign_out(cookie: CookieModel, cookie_name: str) -> NoReturn:
    """Clear the session, delete a sent cookie once, show the login form and stop."""
    st.session_state.pop(SESSION_USER_KEY, None)
    st.session_state.pop(USERNAME_KEY, None)
    st.session_state.pop(EXPIRES_KEY, None)
    reset_current_tenant()
    # The request cookies stay stale until the browser reloads. The logout flag
    # makes the cookie unread from now on, so the delete runs only once and never
    # in the same rerun as the set_cookie of a new login.
    if not st.session_state[LOGOUT_KEY] and _cookie_sent(cookie_name):
        cookie.delete_cookie()
        st.session_state[LOGOUT_KEY] = True
    login_form(cookie)
    st.stop()


def require_auth() -> dict[str, Any]:
    """Return the signed-in user read from the database, or show the login form and stop."""
    settings = get_settings()
    st.session_state.setdefault(LOGOUT_KEY, False)
    cookie = CookieModel(
        settings.auth_cookie_name, settings.auth_cookie_key, settings.auth_cookie_expiry_days
    )
    user = _session_user(cookie)
    if user is None:
        _sign_out(cookie, settings.auth_cookie_name)
    st.session_state[SESSION_USER_KEY] = user
    set_current_tenant(user["tenant_id"])
    logout_button(cookie)
    return user


def get_current_user() -> dict[str, Any] | None:
    """Return the session user dict, or None."""
    user = st.session_state.get(SESSION_USER_KEY)
    return user if isinstance(user, dict) else None


def logout_button(cookie: CookieModel) -> None:
    """Show a sidebar logout button; on click revoke the session, then clear it and the cookie."""
    if not st.sidebar.button("Log out", key="logout_button"):
        return
    user = get_current_user()
    if user is not None:
        # Revocation must never look successful when it failed: keep the session to retry.
        try:
            _store().bump_session_version(user["id"])
        except SQLAlchemyError:
            st.error("Logout failed: the database is unavailable. Try again.")
            return
    st.session_state.pop(SESSION_USER_KEY, None)
    st.session_state.pop(USERNAME_KEY, None)
    st.session_state.pop(EXPIRES_KEY, None)
    st.session_state[LOGOUT_KEY] = True
    reset_current_tenant()
    cookie.delete_cookie()
    st.rerun()


def current_role() -> str:
    """Return the session user's role, or "" when it is missing or malformed."""
    user = st.session_state.get(SESSION_USER_KEY)
    if not isinstance(user, dict):
        return ""
    role = user.get("role")
    return role if isinstance(role, str) else ""


def require_admin() -> None:
    """Stop the page with a warning unless the session user is an admin."""
    if not is_admin(current_role()):
        st.warning("Admin role required.")
        st.stop()
