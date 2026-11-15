"""Login throttle against a live Valkey (``settings.redis_url``) and PostgreSQL.

Marked ``integration``. Each test uses unique emails, so its keys are unique, and
deletes them afterwards. Skipped if Valkey or PostgreSQL is unreachable.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable, Iterator
from typing import Any
from unittest.mock import patch

import pytest
import redis
from factories.auth import KEY, FakeCookie
from redis.exceptions import RedisError
from streamlit.testing.v1 import AppTest

from config.settings import get_settings
from core.security import tenant_context
from core.security.login_throttle import LoginThrottle, _key
from plugins.relational_db.postgres import PostgreSQLStore
from ui.components import auth

pytestmark = pytest.mark.integration

TENANT = "login-throttle-test"
PLAIN = "secret-pass"
OwnerSql = Callable[..., list[Any]]


def _client() -> redis.Redis:
    return redis.Redis.from_url(
        get_settings().redis_url, socket_timeout=1, socket_connect_timeout=1
    )


@pytest.fixture
def valkey() -> Iterator[tuple[redis.Redis, list[str]]]:
    """Live client and a list of emails whose keys are deleted afterwards."""
    client = _client()
    try:
        client.ping()
    except RedisError:
        pytest.skip("Valkey unreachable")
    emails: list[str] = []
    yield client, emails
    for email in emails:
        client.delete(_key(email))
    client.close()


def _email(emails: list[str]) -> str:
    email = f"throttle-{uuid.uuid4().hex[:12]}@example.com"
    emails.append(email)
    return email


def test_lock_survives_new_client(valkey: tuple[redis.Redis, list[str]]) -> None:
    client, emails = valkey
    email = _email(emails)
    first = LoginThrottle(client, 2, 60, 60)
    assert [first.record_failure(email) for _ in range(2)] == [False, True]

    other = _client()
    assert LoginThrottle(other, 2, 60, 60).is_locked(email.upper())
    other.close()


def test_window_is_not_extended_by_later_failure(valkey: tuple[redis.Redis, list[str]]) -> None:
    client, emails = valkey
    email = _email(emails)
    throttle = LoginThrottle(client, 5, 2, 60)
    throttle.record_failure(email)
    time.sleep(1.2)
    throttle.record_failure(email)
    time.sleep(1.0)
    assert client.get(_key(email)) is None


@pytest.fixture
def store(
    postgres_url: str,
    owner_sql: OwnerSql,
    valkey: tuple[redis.Redis, list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[PostgreSQLStore]:
    """Real store and real Valkey behind the auth adapter; 2-second throttle settings."""
    monkeypatch.setenv("AUTH_COOKIE_KEY", KEY)
    monkeypatch.setenv("BCRYPT_ROUNDS", "4")
    monkeypatch.setenv("LOGIN_MAX_FAILURES", "2")
    monkeypatch.setenv("LOGIN_WINDOW_SECONDS", "2")
    monkeypatch.setenv("LOGIN_LOCKOUT_SECONDS", "2")
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


def _script() -> None:
    import streamlit as st

    from ui.components.auth import require_auth

    st.markdown(f"hello {require_auth()['role']}")


def _login(email: str, password: str = PLAIN) -> AppTest:
    at = AppTest.from_function(_script).run()
    at.text_input(key="login_email").input(email)
    at.text_input(key="login_password").input(password)
    at.button[0].click()
    return at.run()


def _logged_in(at: AppTest) -> bool:
    return any("hello admin" in str(m.value) for m in at.markdown)


def test_correct_password_works_after_lock_expires(
    store: PostgreSQLStore, valkey: tuple[redis.Redis, list[str]]
) -> None:
    email = _email(valkey[1])
    with tenant_context(TENANT):
        store.create_user(email=email, password=PLAIN, role="admin", tenant_id=TENANT)
    for _ in range(2):
        assert [e.value for e in _login(email, "wrong").error] == ["Invalid email or password."]

    locked = _login(email)
    assert [e.value for e in locked.error] == ["Invalid email or password."]
    assert not _logged_in(locked)

    time.sleep(2.2)
    assert _logged_in(_login(email))
    assert valkey[0].get(_key(email)) is None
