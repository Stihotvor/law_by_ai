"""Session and cookie checks on each rerun."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import jwt
import pytest
import streamlit as st
from factories.auth import (
    COOKIE,
    KEY,
    LoginEnv,
    login,
    login_form_shown,
    login_row,
    make_token,
    open_page,
    text,
)
from freezegun import freeze_time
from streamlit.testing.v1 import AppTest

from ui.components import auth


def test_cookie_logs_in_without_form(login_env: LoginEnv) -> None:
    login_env.jar[COOKIE] = make_token("admin@x.com|3")
    at = open_page()
    assert "hello admin same=True" in text(at)
    login_env.set_tenant.assert_called_with("t-1")


def test_deactivated_user_loses_session(login_env: LoginEnv) -> None:
    at = login(open_page(), "admin@x.com")
    login_env.store.rows["admin@x.com"] = login_row(is_active=False, session_version=4)
    at.run()
    assert login_form_shown(at)
    assert "user" not in at.session_state
    login_env.reset_tenant.assert_called()


def test_password_change_ends_live_session(login_env: LoginEnv) -> None:
    at = login(open_page(), "admin@x.com")
    login_env.store.rows["admin@x.com"] = login_row(session_version=4)
    at.run()
    assert login_form_shown(at)
    assert "user" not in at.session_state


def test_stale_cookie_is_rejected_and_deleted(login_env: LoginEnv) -> None:
    stale = make_token("admin@x.com|2")
    login_env.jar[COOKIE] = stale
    at = open_page()
    assert login_form_shown(at)
    assert "user" not in at.session_state
    assert login_env.jar == {}
    assert login_env.deleted == 1
    login_env.jar[COOKIE] = stale  # the request cookies keep the old copy until reload
    at.run()
    assert login_env.deleted == 1


def test_open_session_ends_when_cookie_expiry_passes(login_env: LoginEnv) -> None:
    with freeze_time("2026-01-01") as frozen:
        at = login(open_page(), "admin@x.com")
        frozen.tick(timedelta(days=29))
        at.run()
        assert "hello admin" in text(at)
        frozen.tick(timedelta(days=1, seconds=1))
        at.run()
        assert login_form_shown(at)
        assert "user" not in at.session_state
        assert "username" not in at.session_state
        assert "auth_expires" not in at.session_state
        login_env.reset_tenant.assert_called()


def test_expired_cookie_shows_login_form(login_env: LoginEnv) -> None:
    login_env.jar[COOKIE] = make_token("admin@x.com|3", exp_date=1.0)
    at = open_page()
    assert login_form_shown(at)
    assert "user" not in at.session_state


def test_no_cookie_is_not_deleted(login_env: LoginEnv) -> None:
    at = open_page()
    at.run()
    assert login_form_shown(at)
    assert login_env.deleted == 0


@pytest.mark.parametrize(
    "token",
    [
        make_token("admin@x.com"),
        make_token("admin@x.com|three"),
        make_token("admin@x.com|3", key="w" * 32),
        make_token("admin@x.com|3", key="k" * 64, alg="HS512"),
        jwt.encode({"username": "admin@x.com|3", "exp_date": 9e9}, "", algorithm="none"),
        jwt.encode({"exp_date": 9e9}, KEY, algorithm="HS256"),
        "not-a-jwt",
    ],
)
def test_malformed_cookie_shows_login_form(login_env: LoginEnv, token: str) -> None:
    login_env.jar[COOKIE] = token
    at = open_page()
    assert not at.exception
    assert login_form_shown(at)
    assert "user" not in at.session_state


def test_get_current_user_reads_only_session() -> None:
    at = AppTest.from_string(
        "import streamlit as st\n"
        "from ui.components.auth import get_current_user\n"
        "st.markdown(f'u={get_current_user()}')\n"
    )
    at.session_state["user"] = ["admin"]
    assert "u=None" in text(at.run())


def test_cookie_sent_reads_request_cookies() -> None:
    with patch.object(st, "context") as context:
        context.cookies = {COOKIE: "token"}
        assert auth._cookie_sent(COOKIE)
        assert not auth._cookie_sent("other")
