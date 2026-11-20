"""Auth test doubles: fake cookie, fake login store, login row builder and ``Stopped``."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar
from unittest.mock import MagicMock

import bcrypt
import jwt
import streamlit as st

KEY = "k" * 32
COOKIE = "law_by_ai_auth"


def make_token(username: str, key: str = KEY, alg: str = "HS256", **extra: Any) -> str:
    """Return a signed cookie value like the one ``CookieModel.set_cookie`` writes."""
    return jwt.encode({"username": username, "exp_date": 9e9, **extra}, key, algorithm=alg)


class FakeCookie:
    """Stand-in for ``CookieModel``: same get/set/delete rules; ``jar`` is the browser."""

    jar: ClassVar[dict[str, str]] = {}
    deleted: ClassVar[int] = 0

    def __init__(self, cookie_name: str, cookie_key: str, cookie_expiry_days: int) -> None:
        self.name, self.key = cookie_name, cookie_key

    @classmethod
    def reset(cls) -> None:
        cls.jar.clear()
        cls.deleted = 0

    def get_cookie(self) -> dict[str, Any] | bool | None:
        if st.session_state["logout"]:
            return False
        token = self.jar.get(self.name)
        if token is None:
            return None
        try:
            data = jwt.decode(token, self.key, algorithms=["HS256"])
        except (jwt.DecodeError, jwt.InvalidSignatureError):
            return None
        # Like CookieModel: an expired token reads as no cookie.
        return data if data.get("exp_date", 0) > datetime.now().timestamp() else None

    def set_cookie(self) -> None:
        self.jar[self.name] = make_token(st.session_state["username"], self.key)

    def delete_cookie(self) -> None:
        type(self).deleted += 1
        self.jar.pop(self.name, None)


SESSION_VERSION = 3
PLAIN = "right-pass"
HASH = bcrypt.hashpw(PLAIN.encode(), bcrypt.gensalt(rounds=4)).decode()


class Stopped(Exception):
    """Raised by the ``st.stop`` stub."""


def login_row(email: str = "admin@x.com", **kw: Any) -> dict[str, Any]:
    """Login row as returned by ``get_login_user``; ``PLAIN`` is the password."""
    row = {
        "id": "u-1",
        "tenant_id": "t-1",
        "email": email,
        "name": "Admin",
        "role": "admin",
        "password_hash": HASH,
        "is_active": True,
        "session_version": SESSION_VERSION,
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
        for row in self.rows.values():
            if row["id"] == user_id:
                row["session_version"] += 1

    def get_login_user(self, email: str) -> dict[str, Any] | None:
        if self.error is not None:
            raise self.error
        return self.rows.get(email.strip().lower())


@dataclass
class LoginEnv:
    store: FakeStore
    set_tenant: MagicMock
    reset_tenant: MagicMock
    jar: dict[str, str]

    @property
    def deleted(self) -> int:
        return FakeCookie.deleted
