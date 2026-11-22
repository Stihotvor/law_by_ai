"""Users page and the per-actor create limit: wiring and fixed messages.

No database and no Redis: ``core.users.UserService`` is a ``MagicMock`` and the
store and Redis client behind ``get_store`` and ``get_redis`` are sentinels.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from streamlit.testing.v1 import AppTest

from core.users import UserCreateThrottledError

PAGE = str(Path(__file__).resolve().parents[3] / "src" / "ui" / "pages" / "users.py")
STORE = object()
REDIS = object()
THROTTLED = "Too many new users in a short time. Try again later."
UNAVAILABLE = "User creation unavailable. Try again later."
RAW = "redis://:secret-pw@cache:6379"


@pytest.fixture
def factory() -> Iterator[MagicMock]:
    """Patched ``UserService`` class; its instance lists no users."""
    fake = MagicMock()
    fake.return_value.list_users.return_value = []
    with (
        patch("core.users.UserService", fake),
        patch("ui.components.auth._store", lambda: STORE),
        patch("ui.components.auth._redis_client", lambda: REDIS),
    ):
        yield fake


def _create() -> AppTest:
    at = AppTest.from_file(PAGE)
    at.session_state["user"] = {"role": "admin"}
    at = at.run()
    at.text_input(key="new_user_email").input("new@x.com")
    at.text_input(key="new_user_initial_cred").input("very-secret-password-1")
    next(b for b in at.button if b.label == "Create user").click()
    return at.run()


def _text(at: AppTest) -> str:
    return " ".join(str(e.value) for e in [*at.markdown, *at.text, *at.error, *at.success])


def test_service_gets_store_and_actor_throttle_from_settings(
    factory: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("USER_CREATE_MAX", "7")
    monkeypatch.setenv("USER_CREATE_WINDOW_SECONDS", "120")
    with patch("core.security.actor_throttle.ActorThrottle") as throttle:
        at = AppTest.from_file(PAGE)
        at.session_state["user"] = {"role": "admin"}
        at.run()
    throttle.assert_called_with(REDIS, 7, 120, "user:create:")
    factory.assert_called_with(STORE, throttle.return_value)


def test_throttled_create_shows_fixed_message(factory: MagicMock) -> None:
    factory.return_value.create_user.side_effect = UserCreateThrottledError("raw throttle text")
    at = _create()
    assert not at.exception
    assert [e.value for e in at.error] == [THROTTLED]
    assert "raw throttle text" not in _text(at)


def test_redis_error_shows_unavailable_and_logs_only_the_class_name(
    factory: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    factory.return_value.create_user.side_effect = RedisConnectionError(RAW)
    at = _create()
    assert not at.exception
    assert [e.value for e in at.error] == [UNAVAILABLE]
    assert "secret-pw" not in _text(at)
    logged = [r.getMessage() for r in caplog.records]
    assert "user create throttle unavailable: ConnectionError" in logged
    assert not any("secret-pw" in m for m in logged)
    assert all(r.exc_info is None for r in caplog.records)
