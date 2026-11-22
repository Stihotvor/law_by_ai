"""Users page: an admin lists, creates and deactivates users of the current tenant.

The page is a thin layer over ``UserService``. The tenant comes from the login
context, never from a form field. Every known error maps to a fixed message; raw
error text, stack traces, passwords and password hashes are never shown.

Actions run in the script body after ``require_admin``, never in widget
callbacks: Streamlit runs callbacks before the script, so a callback would skip
the auth checks of this rerun.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from typing import Any

import streamlit as st
from redis.exceptions import RedisError

from config.settings import get_settings
from core.security import PrincipalRequiredError
from core.security.actor_throttle import ActorThrottle
from core.security.passwords import MAX_PASSWORD_BYTES, MIN_PASSWORD_CHARS
from core.users import (
    LastAdminError,
    SelfDeactivationError,
    UserCreateRefusedError,
    UserCreateThrottledError,
    UserNotFoundError,
    UserService,
)
from ui.components.auth import get_redis, get_store, require_admin

logger = logging.getLogger(__name__)

EMAIL_KEY = "new_user_email"
NAME_KEY = "new_user_name"
ROLE_KEY = "new_user_role"
INITIAL_CRED_KEY = "new_user_initial_cred"
CLEAR_CRED_KEY = "users_clear_initial_cred"
FLASH_KEY = "users_flash"
ROLES = ("user", "admin")
CREATE_KEY_PREFIX = "user:create:"
_PASSWORD_HELP = f"At least {MIN_PASSWORD_CHARS} characters and at most {MAX_PASSWORD_BYTES} bytes."
# The commit outcome of a failed action can be unknown: ask for a check first.
_DB_ERROR = (
    "Database error. The action may have succeeded. Check the user list before you try again."
)
# The create limit lives in Redis: when Redis is down, no user is created (fail closed).
_LIMIT_DOWN = "User creation unavailable. Try again later."
_MESSAGES: dict[type[Exception], str] = {
    UserCreateRefusedError: "Cannot create this user.",
    UserCreateThrottledError: "Too many new users in a short time. Try again later.",
    UserNotFoundError: "User not found.",
    SelfDeactivationError: "You cannot deactivate yourself.",
    LastAdminError: "Cannot deactivate the last admin.",
    PrincipalRequiredError: "Admin role required.",
}
_COLUMNS = ("Email", "Name", "Role", "Status", "")
_WIDTHS = (3, 2, 1, 1, 1)


def _service() -> UserService:
    s = get_settings()
    limiter = ActorThrottle(
        get_redis(), s.user_create_max, s.user_create_window_seconds, CREATE_KEY_PREFIX
    )
    return UserService(get_store(), limiter)


def _message(exc: Exception) -> str:
    """Return the fixed message for *exc*; any other error logs only its class name."""
    if isinstance(exc, RedisError):
        logger.error("user create throttle unavailable: %s", type(exc).__name__)
        return _LIMIT_DOWN
    for kind, text in _MESSAGES.items():
        if isinstance(exc, kind):
            return text
    logger.error("user admin action failed: %s", type(exc).__name__)
    return _DB_ERROR


def _run(action: Callable[[], object], success: str) -> None:
    """Run one service action, keep its outcome for the next render and rerun.

    Every error becomes a fixed message: raw text and stack traces are never shown
    or logged.
    """
    try:
        action()
    except Exception as exc:
        st.session_state[FLASH_KEY] = ("error", _message(exc))
    else:
        st.session_state[FLASH_KEY] = ("success", success)
    st.rerun()


def _show_flash() -> None:
    flash = st.session_state.pop(FLASH_KEY, None)
    if flash is None:
        return
    kind, text = flash
    (st.error if kind == "error" else st.success)(text)


def _create_form() -> None:
    """Show the create form; on submit create the user and clear the password."""
    if st.session_state.pop(CLEAR_CRED_KEY, False):
        st.session_state[INITIAL_CRED_KEY] = ""
    with st.form("create_user"):
        email = st.text_input("Email", key=EMAIL_KEY)
        name = st.text_input("Name", key=NAME_KEY)
        role = str(st.selectbox("Role", ROLES, key=ROLE_KEY))
        password = st.text_input(
            "Password", type="password", key=INITIAL_CRED_KEY, help=_PASSWORD_HELP
        )
        submitted = st.form_submit_button("Create user")
    if not submitted:
        return
    st.session_state[CLEAR_CRED_KEY] = True
    _run(lambda: _service().create_user(email, password, role, name), "User created.")


def _row(user: Mapping[str, Any]) -> None:
    """Show one user from an explicit field list; other fields are never shown."""
    active = bool(user["is_active"])
    cells = st.columns(_WIDTHS)
    cells[0].text(str(user["email"]))
    cells[1].text(str(user["name"]))
    cells[2].text(str(user["role"]))
    cells[3].text("active" if active else "inactive")
    if not active:
        return
    user_id = str(user["id"])
    if cells[4].button("Deactivate", key=f"deactivate_{user_id}"):
        _run(lambda: _service().deactivate_user(user_id), "User deactivated.")


def _user_table() -> None:
    try:
        users = _service().list_users()
    except Exception as exc:
        st.error(_message(exc))
        return
    for cell, title in zip(st.columns(_WIDTHS), _COLUMNS, strict=True):
        cell.markdown(f"**{title}**" if title else "")
    for user in users:
        _row(user)


require_admin()
st.title("Users")
_show_flash()
st.subheader("Create a user")
_create_form()
st.subheader("Users of this tenant")
_user_table()
