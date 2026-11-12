"""Streamlit auth adapter: role guard, login, logout and the signed session cookie.

No database and no browser: a fake store replaces ``get_login_user`` and a fake
cookie class (tests/factories/auth.py) replaces ``CookieModel``.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import bcrypt
import jwt
import pytest
import streamlit as st
from factories.auth import COOKIE, KEY, FakeCookie, make_token
from sqlalchemy.exc import OperationalError, ProgrammingError, SQLAlchemyError
from streamlit.testing.v1 import AppTest

from core.security.passwords import DUMMY_HASH, check_password
from ui.components import auth

_UNSET = object()
APP = str(Path(__file__).resolve().parents[2] / "src" / "ui" / "app.py")
PLAIN = "right-pass"
HASH = bcrypt.hashpw(PLAIN.encode(), bcrypt.gensalt(rounds=4)).decode()
FAILED = "Invalid email or password."


# --- role guard -------------------------------------------------------------


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


def _text(at: AppTest) -> str:
    return " ".join(str(m.value) for m in at.markdown)


def test_admin_sees_page() -> None:
    at = _run({"role": "admin"})
    assert "role=[admin]" in _text(at)
    assert "admin content" in _text(at)
    assert len(at.warning) == 0


def test_user_is_stopped_with_warning() -> None:
    at = _run({"role": "user"})
    assert "role=[user]" in _text(at)
    assert "admin content" not in _text(at)
    assert len(at.warning) == 1


def test_no_session_user_is_stopped_with_warning() -> None:
    at = _run(_UNSET)
    assert "role=[]" in _text(at)
    assert "admin content" not in _text(at)
    assert at.warning[0].value == "Admin role required."


@pytest.mark.parametrize("user", ["admin", None, {"role": 1}, {"name": "x"}, ["admin"]])
def test_malformed_session_user_fails_closed(user: Any) -> None:
    at = _run(user)
    assert "role=[]" in _text(at)
    assert "admin content" not in _text(at)
    assert len(at.warning) == 1


# --- fakes ------------------------------------------------------------------


def _row(email: str = "admin@x.com", **kw: Any) -> dict[str, Any]:
    row = {
        "id": "u-1",
        "tenant_id": "t-1",
        "email": email,
        "name": "Admin",
        "role": "admin",
        "password_hash": HASH,
        "is_active": True,
        "session_version": 3,
    }
    return row | kw


@dataclass
class FakeStore:
    rows: dict[str, dict[str, Any]] = field(default_factory=dict)
    error: Exception | None = None
    # (user_id, cookie deletes so far) for each bump: proves the bump runs first.
    bumped: list[tuple[str, int]] = field(default_factory=list)

    bump_error: Exception | None = None

    def bump_session_version(self, user_id: str) -> None:
        if self.bump_error is not None:
            raise self.bump_error
        self.bumped.append((user_id, FakeCookie.deleted))

    def get_login_user(self, email: str) -> dict[str, Any] | None:
        if self.error is not None:
            raise self.error
        return self.rows.get(email.strip().lower())


@dataclass
class Env:
    store: FakeStore
    set_tenant: MagicMock
    reset_tenant: MagicMock
    jar: dict[str, str]

    @property
    def deleted(self) -> int:
        return FakeCookie.deleted


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> Iterator[Env]:
    monkeypatch.setenv("AUTH_COOKIE_KEY", KEY)
    monkeypatch.delenv("AUTH_COOKIE_NAME", raising=False)
    monkeypatch.delenv("AUTH_COOKIE_EXPIRY_DAYS", raising=False)
    store = FakeStore({"admin@x.com": _row(), "user@x.com": _row("user@x.com", role="user")})
    FakeCookie.reset()
    with (
        patch.object(auth, "_store", lambda: store),
        patch.object(auth, "CookieModel", FakeCookie),
        patch.object(auth, "_cookie_sent", lambda name: name in FakeCookie.jar),
        patch.object(auth, "set_current_tenant") as set_tenant,
        patch.object(auth, "reset_current_tenant") as reset_tenant,
    ):
        yield Env(store, set_tenant, reset_tenant, FakeCookie.jar)


def _auth_script() -> None:
    import streamlit as st

    from ui.components.auth import get_current_user, require_auth

    user = require_auth()
    st.markdown(f"hello {user['role']} same={get_current_user() == user}")


def _open() -> AppTest:
    return AppTest.from_function(_auth_script).run()


def _login(at: AppTest, email: str, password: str = PLAIN) -> AppTest:
    at.text_input(key="login_email").input(email)
    at.text_input(key="login_password").input(password)
    at.button[0].click()
    return at.run()


def _login_form_shown(at: AppTest) -> bool:
    keys = {t.key for t in at.text_input}
    return {"login_email", "login_password"} <= keys and "hello" not in _text(at)


# --- authenticate -------------------------------------------------------------


def test_authenticate_returns_public_fields_only(env: Env) -> None:
    user = auth.authenticate(" Admin@X.com ", PLAIN)
    assert user == {
        "id": "u-1",
        "tenant_id": "t-1",
        "email": "admin@x.com",
        "name": "Admin",
        "role": "admin",
    }


@pytest.mark.parametrize("change", [{"is_active": False}, {"role": "root"}])
def test_inactive_user_or_invalid_role_is_refused(env: Env, change: dict[str, Any]) -> None:
    env.store.rows["admin@x.com"] = _row(**change)
    assert auth.authenticate("admin@x.com", PLAIN) is None


def test_unknown_email_checks_dummy_hash(env: Env) -> None:
    with patch.object(auth, "check_password", wraps=check_password) as check:
        assert auth.authenticate("nobody@x.com", PLAIN) is None
    check.assert_called_once_with(PLAIN, DUMMY_HASH)


# --- login ------------------------------------------------------------------


def test_admin_logs_in(env: Env) -> None:
    at = _login(_open(), "Admin@X.com")
    assert "hello admin same=True" in _text(at)
    assert at.session_state["username"] == "admin@x.com|3"
    assert jwt.decode(env.jar[COOKIE], KEY, algorithms=["HS256"])["username"] == "admin@x.com|3"
    env.set_tenant.assert_called_with("t-1")
    assert env.deleted == 0


@pytest.mark.parametrize("email", ["admin@x.com", "nobody@x.com"])
def test_wrong_password_or_unknown_email_shows_one_generic_error(env: Env, email: str) -> None:
    at = _login(_open(), email, "wrong")
    assert [e.value for e in at.error] == [FAILED]
    assert "user" not in at.session_state
    assert "username" not in at.session_state
    assert env.jar == {}
    assert _login_form_shown(at)


@pytest.mark.parametrize(
    "error",
    [
        OperationalError("SELECT", {}, Exception("down")),
        ProgrammingError("SELECT", {}, Exception("bad")),
        SQLAlchemyError("other"),
    ],
)
def test_database_error_shows_login_unavailable(env: Env, error: Exception) -> None:
    at = _open()
    env.store.error = error
    at = _login(at, "admin@x.com")
    assert [e.value for e in at.error] == ["Login unavailable. Try again later."]
    assert "user" not in at.session_state
    assert not at.exception


def test_database_down_on_rerun_shows_login_unavailable(env: Env) -> None:
    at = _login(_open(), "admin@x.com")
    env.store.error = OperationalError("SELECT", {}, Exception("down"))
    at.run()
    assert [e.value for e in at.error] == ["Login unavailable. Try again later."]
    assert "hello" not in _text(at)


def test_role_comes_only_from_database_row(env: Env) -> None:
    env.jar[COOKIE] = make_token("user@x.com|3", role="admin")
    at = AppTest.from_function(_auth_script)
    at.query_params["role"] = "admin"
    at.run()
    assert "hello user" in _text(at)
    assert at.session_state["user"]["role"] == "user"


# --- logout -----------------------------------------------------------------


def test_logout_clears_session_tenant_and_cookie(env: Env) -> None:
    at = _login(_open(), "admin@x.com")
    at.button(key="logout_button").click()
    at.run()
    assert "user" not in at.session_state
    assert "username" not in at.session_state
    assert auth.current_role() == ""
    env.reset_tenant.assert_called()
    assert env.jar == {}
    assert _login_form_shown(at)


def test_logout_bumps_session_version_before_cookie_delete(env: Env) -> None:
    at = _login(_open(), "admin@x.com")
    deleted = env.deleted
    at.button(key="logout_button").click()
    at.run()
    assert env.store.bumped == [("u-1", deleted)]
    assert env.deleted == deleted + 1


def test_logout_still_clears_session_when_bump_fails(env: Env) -> None:
    at = _login(_open(), "admin@x.com")
    env.store.bump_error = OperationalError("UPDATE", {}, Exception("down"))
    at.button(key="logout_button").click()
    at.run()
    assert "user" not in at.session_state
    assert env.jar == {}
    assert _login_form_shown(at)


def test_stale_browser_cookie_does_not_log_in_after_logout(env: Env) -> None:
    at = _login(_open(), "admin@x.com")
    token = env.jar[COOKIE]
    at.button(key="logout_button").click()
    at.run()
    env.jar[COOKIE] = token  # the browser still sends the old cookie
    at.run()
    assert _login_form_shown(at)
    assert "user" not in at.session_state


def test_login_after_logout_does_not_delete_new_cookie(env: Env) -> None:
    at = _login(_open(), "admin@x.com")
    at.button(key="logout_button").click()
    at.run()
    deleted = env.deleted
    env.jar[COOKIE] = make_token("admin@x.com|3")  # stale copy still sent
    at = _login(at, "admin@x.com")
    assert "hello admin" in _text(at)
    assert env.deleted == deleted


# --- session and cookie checks on each rerun ------------------------------------


def test_cookie_logs_in_without_form(env: Env) -> None:
    env.jar[COOKIE] = make_token("admin@x.com|3")
    at = _open()
    assert "hello admin same=True" in _text(at)
    env.set_tenant.assert_called_with("t-1")


def test_deactivated_user_loses_session(env: Env) -> None:
    at = _login(_open(), "admin@x.com")
    env.store.rows["admin@x.com"] = _row(is_active=False, session_version=4)
    at.run()
    assert _login_form_shown(at)
    assert "user" not in at.session_state
    env.reset_tenant.assert_called()


def test_password_change_ends_live_session(env: Env) -> None:
    at = _login(_open(), "admin@x.com")
    env.store.rows["admin@x.com"] = _row(session_version=4)
    at.run()
    assert _login_form_shown(at)
    assert "user" not in at.session_state


def test_stale_cookie_is_rejected_and_deleted(env: Env) -> None:
    stale = make_token("admin@x.com|2")
    env.jar[COOKIE] = stale
    at = _open()
    assert _login_form_shown(at)
    assert "user" not in at.session_state
    assert env.jar == {}
    assert env.deleted == 1
    env.jar[COOKIE] = stale  # the request cookies keep the old copy until reload
    at.run()
    assert env.deleted == 1


def test_no_cookie_is_not_deleted(env: Env) -> None:
    at = _open()
    at.run()
    assert _login_form_shown(at)
    assert env.deleted == 0


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
def test_malformed_cookie_shows_login_form(env: Env, token: str) -> None:
    env.jar[COOKIE] = token
    at = _open()
    assert not at.exception
    assert _login_form_shown(at)
    assert "user" not in at.session_state


def test_get_current_user_reads_only_session() -> None:
    at = AppTest.from_string(
        "import streamlit as st\n"
        "from ui.components.auth import get_current_user\n"
        "st.markdown(f'u={get_current_user()}')\n"
    )
    at.session_state["user"] = ["admin"]
    assert "u=None" in _text(at.run())


def test_cookie_sent_reads_request_cookies() -> None:
    with patch.object(st, "context") as context:
        context.cookies = {COOKIE: "token"}
        assert auth._cookie_sent(COOKIE)
        assert not auth._cookie_sent("other")


# --- app ----------------------------------------------------------------------


def _app() -> AppTest:
    return AppTest.from_file(APP).run()


def test_admin_reaches_fetch_form(env: Env) -> None:
    at = _login(_app(), "admin@x.com")
    at.switch_page("pages/fetch.py").run()
    assert not at.exception
    assert any(b.label == "Fetch" for b in at.button)


def test_user_has_no_fetch_page(env: Env) -> None:
    at = _login(_app(), "user@x.com")
    assert not at.exception
    assert [t.value for t in at.title] == ["Law by AI"]
    assert not any(b.label == "Fetch" for b in at.button)
    with pytest.raises(ValueError, match=r"Known pages: \['Home'\]"):
        at.switch_page("pages/fetch.py")


def test_app_shows_login_form_without_session(env: Env) -> None:
    at = _app()
    assert not at.exception
    assert _login_form_shown(at)


@pytest.mark.parametrize(
    ("name", "value"),
    [("AUTH_COOKIE_KEY", "some_key"), ("AUTH_COOKIE_EXPIRY_DAYS", "0")],
)
def test_bad_auth_setting_fails_before_navigation(
    env: Env, monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv(name, value)
    with patch("streamlit.navigation") as navigation:
        at = _app()
    assert at.exception
    navigation.assert_not_called()
    assert env.deleted == 0
