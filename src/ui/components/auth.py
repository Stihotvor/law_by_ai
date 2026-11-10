"""Streamlit auth adapter (ADR-0013): read the session role and guard admin pages."""

from __future__ import annotations

import streamlit as st

from core.security.rbac import is_admin

# Session key that holds the signed-in user dict. This is a stub until the login UI exists.
# Nothing may write this key from user-controlled input (form fields, query params, cookies).
# The login UI must set it only from the authenticator's verified result.
SESSION_USER_KEY = "user"


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
