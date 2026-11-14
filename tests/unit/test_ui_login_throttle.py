"""Login form throttle: per-email lock in Redis and the per-session failure limit.

No database, no Redis and no browser: a fake store, a hand-written Redis fake
(tests/fakes/valkey.py) and the fake cookie (tests/factories/auth.py).
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any
from unittest.mock import patch

import bcrypt
import pytest
from factories.auth import KEY, FakeCookie
from fakes.valkey import FakeRedis
from freezegun import freeze_time
from redis.exceptions import ConnectionError as RedisConnectionError
from streamlit.testing.v1 import AppTest

from core.security.login_throttle import LoginThrottle
from ui.components import auth

PLAIN = "right-pass"
SECRET = "wrong-secret-xyz"  # noqa: S105 - a wrong password the logs must not contain
HASH = bcrypt.hashpw(PLAIN.encode(), bcrypt.gensalt(rounds=4)).decode()
FAILED = "Invalid email or password."
UNAVAILABLE = "Login unavailable. Try again later."
MAX = 3


def _row(email: str) -> dict[str, Any]:
    return {
        "id": f"id-{email}",
        "tenant_id": "t-1",
        "email": email,
        "name": "N",
        "role": "admin",
        "password_hash": HASH,
        "is_active": True,
        "session_version": 1,
    }


@dataclass
class Store:
    rows: dict[str, dict[str, Any]]
    lookups: list[str] = field(default_factory=list)

    def get_login_user(self, email: str) -> dict[str, Any] | None:
        self.lookups.append(email)
        return self.rows.get(email.strip().lower())


@dataclass
class Env:
    store: Store
    redis: FakeRedis

    def throttle(self) -> LoginThrottle:
        return LoginThrottle(self.redis, MAX, 60, 300)


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> Iterator[Env]:
    monkeypatch.setenv("AUTH_COOKIE_KEY", KEY)
    monkeypatch.setenv("LOGIN_MAX_FAILURES", str(MAX))
    monkeypatch.setenv("LOGIN_WINDOW_SECONDS", "60")
    monkeypatch.setenv("LOGIN_LOCKOUT_SECONDS", "300")
    store = Store({e: _row(e) for e in ("a@x.com", "b@x.com")})
    client = FakeRedis()
    FakeCookie.reset()
    with (
        patch.object(auth, "_store", lambda: store),
        patch.object(auth, "_redis_client", lambda: client),
        patch.object(auth, "CookieModel", FakeCookie),
        patch.object(auth, "_cookie_sent", lambda name: name in FakeCookie.jar),
        patch.object(auth, "set_current_tenant"),
        patch.object(auth, "reset_current_tenant"),
    ):
        yield Env(store, client)


def _script() -> None:
    import streamlit as st

    from ui.components.auth import require_auth

    st.markdown(f"hello {require_auth()['email']}")


def _login(email: str, password: str = PLAIN, at: AppTest | None = None) -> AppTest:
    at = at or AppTest.from_function(_script).run()
    at.text_input(key="login_email").input(email)
    at.text_input(key="login_password").input(password)
    at.button[0].click()
    return at.run()


def _errors(at: AppTest) -> list[str]:
    return [str(e.value) for e in at.error]


def _logged_in(at: AppTest) -> bool:
    return any("hello" in str(m.value) for m in at.markdown)


def _fail_in_new_sessions(email: str, times: int = MAX) -> None:
    for _ in range(times):
        assert _errors(_login(email, "wrong")) == [FAILED]


@pytest.mark.parametrize("email", ["a@x.com", "nobody@x.com"])
def test_email_locks_after_max_failures(env: Env, email: str) -> None:
    _fail_in_new_sessions(email)
    assert env.throttle().is_locked(email)
    at = _login(email.upper())
    assert _errors(at) == [FAILED]
    assert not _logged_in(at)


def test_locked_email_skips_lookup_and_bcrypt(env: Env) -> None:
    _fail_in_new_sessions("a@x.com")
    env.store.lookups.clear()
    with (
        patch.object(auth, "check_password") as check,
        patch.object(auth, "_verify", wraps=auth._verify) as verify,
    ):
        at = _login("a@x.com")
    assert _errors(at) == [FAILED]
    verify.assert_not_called()
    check.assert_not_called()
    assert env.store.lookups == []


def test_success_resets_failures(env: Env) -> None:
    _fail_in_new_sessions("a@x.com", MAX - 1)
    assert _logged_in(_login("a@x.com"))
    assert env.redis.values == {}


def test_success_clears_session_failures(env: Env) -> None:
    at = AppTest.from_function(_script).run()
    for i in range(MAX - 1):
        at = _login(f"spray{i}@x.com", "wrong", at)
    at = _login("a@x.com", PLAIN, at)
    assert _logged_in(at)
    assert auth.LOGIN_FAILURES_KEY not in at.session_state


def test_lock_expires(env: Env) -> None:
    with freeze_time("2026-01-01") as frozen:
        _fail_in_new_sessions("a@x.com")
        frozen.tick(timedelta(seconds=301))
        assert _logged_in(_login("a@x.com"))


def test_session_spray_is_limited(env: Env) -> None:
    at = AppTest.from_function(_script).run()
    for i in range(MAX):
        at = _login(f"spray{i}@x.com", "wrong", at)
    env.store.lookups.clear()
    at = _login("b@x.com", PLAIN, at)
    assert _errors(at) == [FAILED]
    assert not _logged_in(at)
    assert env.store.lookups == []
    assert not env.throttle().is_locked("b@x.com")


def test_session_limit_ends_after_window(env: Env) -> None:
    with freeze_time("2026-01-01") as frozen:
        at = AppTest.from_function(_script).run()
        for i in range(MAX):
            at = _login(f"spray{i}@x.com", "wrong", at)
        frozen.tick(timedelta(seconds=61))
        assert _logged_in(_login("b@x.com", PLAIN, at))


@pytest.mark.parametrize(
    ("method", "password"),
    [("is_locked", PLAIN), ("record_failure", "wrong"), ("reset", PLAIN)],
)
def test_redis_error_shows_login_unavailable(env: Env, method: str, password: str) -> None:
    with patch.object(LoginThrottle, method, side_effect=RedisConnectionError("down")):
        at = _login("a@x.com", password)
    assert _errors(at) == [UNAVAILABLE]
    assert not _logged_in(at)
    assert "user" not in at.session_state
    assert not at.exception


def test_redis_outage_shows_login_unavailable(env: Env) -> None:
    env.redis.error = RedisConnectionError("down")
    at = _login("a@x.com")
    assert _errors(at) == [UNAVAILABLE]
    assert not at.exception


@pytest.mark.parametrize(
    ("raw", "logged"),
    [("a\nb@x", "a\\nb@x"), ("a" * 300, "a" * 254), ("ok@x.com", "ok@x.com")],
)
def test_safe_email_caps_and_escapes(raw: str, logged: str) -> None:
    assert auth._safe(raw) == logged


def test_failure_log_escapes_control_characters(env: Env, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger=auth.__name__)
    _login("a\nb@x", "wrong")
    records = [r for r in caplog.records if r.name == auth.__name__]
    assert [getattr(r, "email", None) for r in records] == ["a\\nb@x"]
    assert all("\n" not in str(getattr(r, "email", "")) for r in records)
    assert all("\n" not in r.getMessage() for r in records)


def test_logs_have_email_and_no_password(env: Env, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger=auth.__name__)
    for _ in range(MAX + 1):
        _login(" A@X.com ", SECRET)
    records = [r for r in caplog.records if r.name == auth.__name__]
    events = [r.getMessage() for r in records]
    names = ["login_failed"] * MAX + ["login_locked", "login_rejected_locked"]
    assert events == [f"{name} email=a@x.com" for name in names]
    assert {getattr(r, "email", None) for r in records} == {"a@x.com"}
    assert SECRET not in caplog.text
    assert all(SECRET not in str(r.__dict__) for r in caplog.records)
