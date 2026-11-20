"""Logout: session, tenant and cookie cleanup, and replay of copied cookies."""

from __future__ import annotations

from auth_page_driver import login, login_form_shown, open_page, text
from factories.auth import COOKIE, LoginEnv, make_token
from sqlalchemy.exc import OperationalError

from ui.components import auth

LOGOUT_WARNING = (
    "You are logged out here, but the server could not revoke other copies of your session. "
    "They stay valid until the cookie expires."
)


def test_logout_clears_session_tenant_and_cookie(login_env: LoginEnv) -> None:
    at = login(open_page(), "admin@x.com")
    at.button(key="logout_button").click()
    at.run()
    assert "user" not in at.session_state
    assert "username" not in at.session_state
    assert auth.current_role() == ""
    login_env.reset_tenant.assert_called()
    assert login_env.jar == {}
    assert login_form_shown(at)


def test_logout_bumps_session_version_before_cookie_delete(login_env: LoginEnv) -> None:
    at = login(open_page(), "admin@x.com")
    deleted = login_env.deleted
    at.button(key="logout_button").click()
    at.run()
    assert login_env.store.bumped == [("u-1", deleted)]
    assert login_env.deleted == deleted + 1


def test_logout_clears_locally_and_warns_when_bump_fails(login_env: LoginEnv) -> None:
    at = login(open_page(), "admin@x.com")
    deleted = login_env.deleted
    login_env.store.bump_error = OperationalError("UPDATE", {}, Exception("down"))
    at.button(key="logout_button").click()
    at.run()
    assert "user" not in at.session_state
    assert "username" not in at.session_state
    assert auth.EXPIRES_KEY not in at.session_state
    login_env.reset_tenant.assert_called()
    assert login_env.jar == {}
    assert login_env.deleted == deleted + 1
    assert login_form_shown(at)
    assert [w.value for w in at.warning] == [LOGOUT_WARNING]
    assert auth.LOGOUT_WARNING_KEY not in at.session_state
    at.run()
    assert len(at.warning) == 0


def test_copied_cookie_replayed_in_new_session_after_logout_is_refused(login_env: LoginEnv) -> None:
    at = login(open_page(), "admin@x.com")
    token = login_env.jar[COOKIE]
    at.button(key="logout_button").click()
    at.run()
    assert login_env.store.rows["admin@x.com"]["session_version"] == 4
    login_env.jar[COOKIE] = token
    fresh = open_page()
    assert login_form_shown(fresh)
    assert "user" not in fresh.session_state


def test_stale_browser_cookie_does_not_log_in_after_logout(login_env: LoginEnv) -> None:
    at = login(open_page(), "admin@x.com")
    token = login_env.jar[COOKIE]
    at.button(key="logout_button").click()
    at.run()
    login_env.jar[COOKIE] = token  # the browser still sends the old cookie
    at.run()
    assert login_form_shown(at)
    assert "user" not in at.session_state


def test_login_after_logout_does_not_delete_new_cookie(login_env: LoginEnv) -> None:
    at = login(open_page(), "admin@x.com")
    at.button(key="logout_button").click()
    at.run()
    deleted = login_env.deleted
    login_env.jar[COOKIE] = make_token("admin@x.com|3")  # stale copy still sent
    at = login(at, "admin@x.com")
    assert "hello admin" in text(at)
    assert login_env.deleted == deleted
