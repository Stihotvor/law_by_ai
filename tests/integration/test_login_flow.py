"""Login flow against a live PostgreSQL: real ``PostgreSQLStore``, fake browser cookie.

Marked ``integration``. The store runs as ``lawbyai_app``; the owner
``lawbyai_owner`` changes and deletes rows inside ``TENANT``. A browser reload
is a new ``AppTest`` session that sends the cookie the first session set.
Skipped if PostgreSQL is unreachable.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from typing import Any
from unittest.mock import patch

import pytest
from factories.auth import COOKIE, KEY, FakeCookie
from streamlit.testing.v1 import AppTest

from core.security import tenant_context
from plugins.relational_db.postgres import PostgreSQLStore
from ui.components import auth

pytestmark = pytest.mark.integration

TENANT = "login-flow-test"
PLAIN = "secret-pass"
OwnerSql = Callable[..., list[Any]]


@pytest.fixture
def store(
    postgres_url: str, owner_sql: OwnerSql, monkeypatch: pytest.MonkeyPatch
) -> Iterator[PostgreSQLStore]:
    """Real store behind the auth adapter; deletes the test users afterwards."""
    monkeypatch.setenv("AUTH_COOKIE_KEY", KEY)
    monkeypatch.delenv("AUTH_COOKIE_NAME", raising=False)
    monkeypatch.delenv("AUTH_COOKIE_EXPIRY_DAYS", raising=False)
    monkeypatch.setenv("BCRYPT_ROUNDS", "4")
    FakeCookie.reset()
    s = PostgreSQLStore()
    s.initialize()
    with (
        patch.object(auth, "_store", lambda: s),
        patch.object(auth, "CookieModel", FakeCookie),
        patch.object(auth, "_cookie_sent", lambda name: name in FakeCookie.jar),
    ):
        yield s
    s.close()
    owner_sql(TENANT, "DELETE FROM users WHERE tenant_id = :t", t=TENANT)


def _admin(store: PostgreSQLStore) -> str:
    email = f"admin-{uuid.uuid4().hex[:12]}@example.com"
    with tenant_context(TENANT):
        store.create_user(email=email, password=PLAIN, role="admin", tenant_id=TENANT)
    return email


def _script() -> None:
    import streamlit as st

    from ui.components.auth import require_auth

    user = require_auth()
    st.markdown(f"hello {user['role']} {user['tenant_id']}")


def _text(at: AppTest) -> str:
    return " ".join(str(m.value) for m in at.markdown)


def _login(email: str, password: str = PLAIN) -> AppTest:
    at = AppTest.from_function(_script).run()
    at.text_input(key="login_email").input(email.upper())
    at.text_input(key="login_password").input(password)
    at.button[0].click()
    return at.run()


def _reload() -> AppTest:
    return AppTest.from_function(_script).run()


def test_cookie_survives_browser_reload(store: PostgreSQLStore) -> None:
    _login(_admin(store))
    assert COOKIE in FakeCookie.jar

    at = _reload()

    assert f"hello admin {TENANT}" in _text(at)


def test_wrong_password_sets_nothing(store: PostgreSQLStore) -> None:
    at = _login(_admin(store), "wrong")

    assert len(at.error) == 1
    assert "user" not in at.session_state
    assert FakeCookie.jar == {}


def test_deactivated_user_loses_live_session(store: PostgreSQLStore, owner_sql: OwnerSql) -> None:
    email = _admin(store)
    at = _login(email)
    owner_sql(TENANT, "UPDATE users SET is_active = false WHERE email = :e", e=email)

    at.run()

    assert "hello" not in _text(at)
    assert "user" not in at.session_state


def test_password_change_rejects_copied_cookie(store: PostgreSQLStore, owner_sql: OwnerSql) -> None:
    email = _admin(store)
    _login(email)
    owner_sql(TENANT, "UPDATE users SET password_hash = 'x' WHERE email = :e", e=email)

    at = _reload()

    assert "hello" not in _text(at)
    assert FakeCookie.deleted == 1
