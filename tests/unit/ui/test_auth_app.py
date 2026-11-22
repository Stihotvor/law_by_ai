"""The app entry point: pages by role, login form and bad auth settings."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from auth_page_driver import login_form_shown, submit_login
from factories.auth import LoginEnv
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[3] / "src" / "ui" / "app.py")


def _app() -> AppTest:
    return AppTest.from_file(APP).run()


def test_admin_reaches_fetch_form(login_env: LoginEnv) -> None:
    at = submit_login(_app(), "admin@x.com")
    at.switch_page("pages/fetch.py").run()
    assert not at.exception
    assert any(b.label == "Fetch" for b in at.button)


def test_user_has_no_fetch_page(login_env: LoginEnv) -> None:
    at = submit_login(_app(), "user@x.com")
    assert not at.exception
    assert [t.value for t in at.title] == ["Law by AI"]
    assert not any(b.label == "Fetch" for b in at.button)
    with pytest.raises(ValueError, match=r"Known pages: \['Home'\]"):
        at.switch_page("pages/fetch.py")


def test_app_shows_login_form_without_session(login_env: LoginEnv) -> None:
    at = _app()
    assert not at.exception
    assert login_form_shown(at)


@pytest.mark.parametrize(
    ("name", "value"),
    [("AUTH_COOKIE_KEY", "some_key"), ("AUTH_COOKIE_EXPIRY_DAYS", "0")],
)
def test_bad_auth_setting_fails_before_navigation(
    login_env: LoginEnv, monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv(name, value)
    with patch("streamlit.navigation") as navigation:
        at = _app()
    assert at.exception
    navigation.assert_not_called()
    assert login_env.deleted == 0
