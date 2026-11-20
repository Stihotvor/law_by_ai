"""Role guard: require_admin stops everyone but a well-formed admin session."""

from __future__ import annotations

from typing import Any

import pytest
from factories.auth import text
from streamlit.testing.v1 import AppTest

_UNSET = object()


def _script() -> None:
    import streamlit as st

    from ui.components.auth import current_role, require_admin

    st.markdown(f"role=[{current_role()}]")
    require_admin()
    st.markdown("admin content")


def _run(user: Any) -> AppTest:
    at = AppTest.from_function(_script)
    if user is not _UNSET:
        at.session_state["user"] = user
    return at.run()


def test_admin_sees_page() -> None:
    at = _run({"role": "admin"})
    assert "role=[admin]" in text(at)
    assert "admin content" in text(at)
    assert len(at.warning) == 0


def test_user_is_stopped_with_warning() -> None:
    at = _run({"role": "user"})
    assert "role=[user]" in text(at)
    assert "admin content" not in text(at)
    assert len(at.warning) == 1


def test_no_session_user_is_stopped_with_warning() -> None:
    at = _run(_UNSET)
    assert "role=[]" in text(at)
    assert "admin content" not in text(at)
    assert at.warning[0].value == "Admin role required."


@pytest.mark.parametrize("user", ["admin", None, {"role": 1}, {"name": "x"}, ["admin"]])
def test_malformed_session_user_fails_closed(user: Any) -> None:
    at = _run(user)
    assert "role=[]" in text(at)
    assert "admin content" not in text(at)
    assert len(at.warning) == 1
