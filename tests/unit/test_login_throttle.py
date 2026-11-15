"""Login throttle against a hand-written Redis fake (tests/fakes/valkey.py)."""

from __future__ import annotations

import hashlib
from datetime import timedelta
from typing import Any, ClassVar
from unittest.mock import MagicMock

import pytest
from fakes.valkey import FakeRedis
from freezegun import freeze_time
from redis.exceptions import ConnectionError as RedisConnectionError

from core.security import login_throttle
from core.security.login_throttle import LoginThrottle, normalise_email
from plugins.relational_db import postgres

EMAIL = "user@x.com"


def _throttle(client: FakeRedis, n: int = 3, window: int = 60, lockout: int = 300) -> LoginThrottle:
    return LoginThrottle(client, n, window, lockout)


def _fail(t: LoginThrottle, times: int, email: str = EMAIL) -> list[bool]:
    return [t.record_failure(email) for _ in range(times)]


@pytest.mark.parametrize("raw", ["  User@X.com ", "USER@X.COM", "user@x.com\n"])
def test_normalise_email_strips_and_lowercases(raw: str) -> None:
    assert normalise_email(raw) == "user@x.com"


def test_key_is_sha256_of_normalised_email() -> None:
    client = FakeRedis()
    _throttle(client).record_failure(" User@X.com ")
    digest = hashlib.sha256(b"user@x.com").hexdigest()
    assert list(client.values) == [f"login:fail:{digest}"]


def test_locks_at_max_failures() -> None:
    t = _throttle(FakeRedis())
    assert _fail(t, 2) == [False, False]
    assert not t.is_locked(EMAIL)
    assert t.record_failure(EMAIL) is True
    assert t.is_locked("USER@x.com ")
    assert t.record_failure(EMAIL) is False


def test_other_email_is_not_locked() -> None:
    t = _throttle(FakeRedis())
    _fail(t, 3)
    assert not t.is_locked("other@x.com")


def test_reset_clears_failures() -> None:
    client = FakeRedis()
    t = _throttle(client)
    _fail(t, 3)
    t.reset(EMAIL)
    assert not t.is_locked(EMAIL)
    assert client.values == {}


def test_window_expiry_forgets_failures() -> None:
    with freeze_time("2026-01-01") as frozen:
        t = _throttle(FakeRedis())
        _fail(t, 2)
        frozen.tick(timedelta(seconds=61))
        assert _fail(t, 2) == [False, False]
        assert not t.is_locked(EMAIL)


def test_window_is_not_extended_by_later_failures() -> None:
    with freeze_time("2026-01-01") as frozen:
        t = _throttle(FakeRedis())
        t.record_failure(EMAIL)
        frozen.tick(timedelta(seconds=50))
        t.record_failure(EMAIL)
        frozen.tick(timedelta(seconds=11))
        assert _fail(t, 2) == [False, False]


def test_lock_lasts_lockout_then_expires() -> None:
    with freeze_time("2026-01-01") as frozen:
        t = _throttle(FakeRedis())
        _fail(t, 3)
        frozen.tick(timedelta(seconds=299))
        assert t.is_locked(EMAIL)
        frozen.tick(timedelta(seconds=2))
        assert not t.is_locked(EMAIL)


@pytest.mark.parametrize(
    "call",
    [
        lambda t: t.is_locked(EMAIL),
        lambda t: t.record_failure(EMAIL),
        lambda t: t.reset(EMAIL),
    ],
)
def test_redis_error_propagates(call: Any) -> None:
    client = FakeRedis()
    client.error = RedisConnectionError("down")
    with pytest.raises(RedisConnectionError):
        call(_throttle(client))


def test_store_login_lookup_uses_shared_normalise_email() -> None:
    assert postgres.normalise_email is login_throttle.normalise_email


class _Session:
    params: ClassVar[dict[str, Any]] = {}

    def __init__(self, engine: object) -> None: ...

    def __enter__(self) -> _Session:
        return self

    def __exit__(self, *exc: object) -> None: ...

    def execute(self, sql: object, params: dict[str, Any]) -> MagicMock:
        type(self).params = params
        result = MagicMock()
        result.mappings.return_value.one_or_none.return_value = None
        return result


def test_store_login_lookup_queries_normalised_email(monkeypatch: pytest.MonkeyPatch) -> None:
    store = postgres.PostgreSQLStore.__new__(postgres.PostgreSQLStore)
    monkeypatch.setattr(store, "_ensure_initialized", lambda: None, raising=False)
    monkeypatch.setattr(store, "_engine", None, raising=False)
    monkeypatch.setattr(postgres, "Session", _Session)
    assert store.get_login_user("  User@X.com ") is None
    assert _Session.params == {"email": "user@x.com"}
