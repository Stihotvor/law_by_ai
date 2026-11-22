"""Login form: success, generic failure, database errors and the role source."""

from __future__ import annotations

import jwt
import pytest
from auth_page_driver import auth_script, login_form_shown, markdown_text, open_page, submit_login
from factories.auth import COOKIE, KEY, LoginEnv, make_token
from sqlalchemy.exc import OperationalError, ProgrammingError, SQLAlchemyError
from streamlit.testing.v1 import AppTest

FAILED = "Invalid email or password."


def test_admin_logs_in(login_env: LoginEnv) -> None:
    at = submit_login(open_page(), "Admin@X.com")
    assert "hello admin same=True" in markdown_text(at)
    assert at.session_state["username"] == "admin@x.com|3"
    assert (
        jwt.decode(login_env.jar[COOKIE], KEY, algorithms=["HS256"])["username"] == "admin@x.com|3"
    )
    login_env.set_tenant.assert_called_with("t-1")
    assert login_env.deleted == 0


@pytest.mark.parametrize("email", ["admin@x.com", "nobody@x.com"])
def test_wrong_password_or_unknown_email_shows_one_generic_error(
    login_env: LoginEnv, email: str
) -> None:
    at = submit_login(open_page(), email, "wrong")
    assert [e.value for e in at.error] == [FAILED]
    assert "user" not in at.session_state
    assert "username" not in at.session_state
    assert login_env.jar == {}
    assert login_form_shown(at)


@pytest.mark.parametrize(
    "error",
    [
        OperationalError("SELECT", {}, Exception("down")),
        ProgrammingError("SELECT", {}, Exception("bad")),
        SQLAlchemyError("other"),
    ],
)
def test_database_error_shows_login_unavailable(login_env: LoginEnv, error: Exception) -> None:
    at = open_page()
    login_env.store.error = error
    at = submit_login(at, "admin@x.com")
    assert [e.value for e in at.error] == ["Login unavailable. Try again later."]
    assert "user" not in at.session_state
    assert not at.exception


def test_database_down_on_rerun_shows_login_unavailable(login_env: LoginEnv) -> None:
    at = submit_login(open_page(), "admin@x.com")
    login_env.store.error = OperationalError("SELECT", {}, Exception("down"))
    at.run()
    assert [e.value for e in at.error] == ["Login unavailable. Try again later."]
    assert "hello" not in markdown_text(at)


def test_role_comes_only_from_database_row(login_env: LoginEnv) -> None:
    login_env.jar[COOKIE] = make_token("user@x.com|3", role="admin")
    at = AppTest.from_function(auth_script)
    at.query_params["role"] = "admin"
    at.run()
    assert "hello user" in markdown_text(at)
    assert at.session_state["user"]["role"] == "user"
