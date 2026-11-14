"""Login throttle (ADR-0013): count failed logins per email in Redis and lock the email.

One key per email: ``login:fail:<sha256 of the normalised email>``. The key holds the
failure count. The first failure starts the window; the failure that reaches the limit
sets the lockout time. No Streamlit imports. Every Redis call may raise ``RedisError``.
"""

from __future__ import annotations

import hashlib
from typing import Any, Protocol

KEY_PREFIX = "login:fail:"


class _Pipeline(Protocol):
    def incr(self, name: str, /) -> Any: ...
    def expire(self, name: str, time: int, /, nx: bool = False) -> Any: ...
    def execute(self) -> list[Any]: ...


class RedisClient(Protocol):
    """The ``redis.Redis`` calls the throttle uses."""

    def get(self, name: str, /) -> Any: ...
    def expire(self, name: str, time: int, /) -> Any: ...
    def delete(self, name: str, /) -> Any: ...
    def pipeline(self, transaction: bool = True) -> _Pipeline: ...


def normalise_email(raw: str) -> str:
    """Return *raw* stripped and lower-cased: the one email form for lookups and keys."""
    return raw.strip().lower()


def _key(email: str) -> str:
    digest = hashlib.sha256(normalise_email(email).encode()).hexdigest()
    return f"{KEY_PREFIX}{digest}"


class LoginThrottle:
    """Per-email failure counter. Numbers must be positive (``Settings`` validates them)."""

    def __init__(
        self, client: RedisClient, max_failures: int, window_s: int, lockout_s: int
    ) -> None:
        """Keep the client and the limits."""
        self._client = client
        self._max = max_failures
        self._window = window_s
        self._lockout = lockout_s

    def is_locked(self, email: str) -> bool:
        """Return True when the email has reached the failure limit."""
        value = self._client.get(_key(email))
        return value is not None and int(value) >= self._max

    def record_failure(self, email: str) -> bool:
        """Count one failure; return True only for the failure that starts the lock.

        The lockout EXPIRE is a second call after the pipeline. A Redis error there
        leaves the window TTL, so the lock can end early; the caller fails closed.
        """
        key = _key(email)
        pipe = self._client.pipeline(transaction=True)
        pipe.incr(key)
        pipe.expire(key, self._window, nx=True)
        count = int(pipe.execute()[0])
        if count != self._max:
            return False
        self._client.expire(key, self._lockout)
        return True

    def reset(self, email: str) -> None:
        """Delete the failure count of the email."""
        self._client.delete(_key(email))
