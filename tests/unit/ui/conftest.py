"""Shared fixtures for the Streamlit auth tests."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest
from factories.auth import KEY, FakeCookie, FakeStore, LoginEnv, Stopped, login_row
from fakes.valkey import FakeRedis

from core.security.principal import reset_principal
from ui.components import auth


@pytest.fixture(autouse=True)
def clean_principal() -> Iterator[None]:
    reset_principal()
    yield
    reset_principal()


@pytest.fixture
def fake_st() -> Iterator[MagicMock]:
    """``ui.components.auth.st`` as a MagicMock whose ``stop`` raises ``Stopped``."""
    st = MagicMock()
    st.session_state = {}
    st.stop.side_effect = Stopped
    with (
        patch.object(auth, "st", st),
        patch.object(auth, "set_current_tenant"),
        patch.object(auth, "reset_current_tenant"),
    ):
        yield st


@pytest.fixture
def login_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[LoginEnv]:
    """Fake store, cookie and Redis behind the real Streamlit login flow."""
    monkeypatch.setenv("AUTH_COOKIE_KEY", KEY)
    monkeypatch.delenv("AUTH_COOKIE_NAME", raising=False)
    monkeypatch.delenv("AUTH_COOKIE_EXPIRY_DAYS", raising=False)
    store = FakeStore(
        {
            "admin@x.com": login_row(),
            "user@x.com": login_row("user@x.com", id="u-2", role="user"),
        }
    )
    FakeCookie.reset()
    with (
        patch.object(auth, "_store", lambda: store),
        patch.object(auth, "_redis_client", FakeRedis),
        patch.object(auth, "CookieModel", FakeCookie),
        patch.object(auth, "_cookie_sent", lambda name: name in FakeCookie.jar),
        patch.object(auth, "set_current_tenant") as set_tenant,
        patch.object(auth, "reset_current_tenant") as reset_tenant,
    ):
        yield LoginEnv(store, set_tenant, reset_tenant, FakeCookie.jar)
