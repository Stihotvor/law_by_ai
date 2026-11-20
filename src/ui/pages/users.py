"""Users page: an admin lists, creates and deactivates users of the current tenant.

The page is a thin layer over ``UserService``. The tenant comes from the login
context, never from a form field. Every error maps to a fixed message; raw error
text, stack traces, passwords and password hashes are never shown.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from typing import Any

import streamlit as st

from core.security import PrincipalRequiredError
from core.users import (
    LastAdminError,
    SelfDeactivationError,
    UserCreateRefusedError,
    UserNotFoundError,
    UserService,
)
from ui.components.auth import _store, require_admin

logger = logging.getLogger(__name__)

EMAIL_KEY = "new_user_email"
NAME_KEY = "new_user_name"
ROLE_KEY = "new_user_role"
PASSWORD_KEY = "new_user_password"  # noqa: S105 (a widget key, not a secret)
FLASH_KEY = "users_flash"
ROLES = ("user", "admin")
_DB_ERROR = "Database error. Try again later."
_MESSAGES: dict[type[Exception], str] = {
    UserCreateRefusedError: "Cannot create this user.",
    UserNotFoundError: "User not found.",
    SelfDeactivationError: "You cannot deactivate yourself.",
    LastAdminError: "Cannot deactivate the last admin.",
    PrincipalRequiredError: "Admin role required.",
}
_COLUMNS = ("Email", "Name", "Role", "Status", "")
_WIDTHS = (3, 2, 1, 1, 1)


def _service() -> UserService:
    return UserService(_store())


def _message(exc: Exception) -> str:
    """Return the fixed message for *exc*; log only the class name of unknown errors."""
    for kind, text in _MESSAGES.items():
        if isinstance(exc, kind):
            return text
    logger.error("user admin action failed: %s", type(exc).__name__)
    return _DB_ERROR


def _run(action: Callable[[], object], success: str) -> None:
    """Run one service action and keep its outcome for the next render."""
    try:
        action()
    except Exception as exc:  # every error maps to a fixed message
        st.session_state[FLASH_KEY] = ("error", _message(exc))
        return
    st.session_state[FLASH_KEY] = ("success", success)


def _on_create() -> None:
    """Form callback: create the user, then clear the password field."""
    state = st.session_state
    email, name = str(state.get(EMAIL_KEY, "")), str(state.get(NAME_KEY, ""))
    role, password = str(state.get(ROLE_KEY, ROLES[0])), str(state.get(PASSWORD_KEY, ""))
    state[PASSWORD_KEY] = ""
    _run(lambda: _service().create_user(email, password, role, name), "User created.")


def _on_deactivate(user_id: str) -> None:
    _run(lambda: _service().deactivate_user(user_id), "User deactivated.")


def _show_flash() -> None:
    flash = st.session_state.pop(FLASH_KEY, None)
    if flash is None:
        return
    kind, text = flash
    (st.error if kind == "error" else st.success)(text)


def _create_form() -> None:
    with st.form("create_user"):
        st.text_input("Email", key=EMAIL_KEY)
        st.text_input("Name", key=NAME_KEY)
        st.selectbox("Role", ROLES, key=ROLE_KEY)
        st.text_input("Password", type="password", key=PASSWORD_KEY, help="At least 12 characters.")
        st.form_submit_button("Create user", on_click=_on_create)


def _row(user: Mapping[str, Any]) -> None:
    """Show one user from an explicit field list; other fields are never shown."""
    active = bool(user["is_active"])
    cells = st.columns(_WIDTHS)
    cells[0].text(str(user["email"]))
    cells[1].text(str(user["name"]))
    cells[2].text(str(user["role"]))
    cells[3].text("active" if active else "inactive")
    if active:
        user_id = str(user["id"])
        cells[4].button(
            "Deactivate", key=f"deactivate_{user_id}", on_click=_on_deactivate, args=(user_id,)
        )


def _user_table() -> None:
    try:
        users = _service().list_users()
    except Exception as exc:  # every error maps to a fixed message
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
