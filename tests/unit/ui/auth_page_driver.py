"""Drive the Streamlit login page with AppTest (helpers for tests/unit/ui)."""

from __future__ import annotations

from factories.auth import PLAIN
from streamlit.testing.v1 import AppTest


def auth_script() -> None:
    import streamlit as st

    from ui.components.auth import get_current_user, require_auth

    user = require_auth()
    st.markdown(f"hello {user['role']} same={get_current_user() == user}")


def markdown_text(at: AppTest) -> str:
    return " ".join(str(m.value) for m in at.markdown)


def open_page() -> AppTest:
    return AppTest.from_function(auth_script).run()


def submit_login(at: AppTest, email: str, password: str = PLAIN) -> AppTest:
    at.text_input(key="login_email").input(email)
    at.text_input(key="login_password").input(password)
    at.button[0].click()
    return at.run()


def login_form_shown(at: AppTest) -> bool:
    keys = {t.key for t in at.text_input}
    return {"login_email", "login_password"} <= keys and "hello" not in markdown_text(at)
