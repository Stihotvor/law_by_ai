"""Fake auth cookie for the login tests: ``CookieModel`` rules without a browser."""

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar

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
