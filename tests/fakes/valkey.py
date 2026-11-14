"""Hand-written Redis fake for the login throttle: GET, INCR, EXPIRE (NX), DEL, pipeline.

Time comes from ``time.time`` so ``freeze_time`` moves key expiry. ``error`` makes every
command raise, like a Redis outage.
"""

from __future__ import annotations

import time
from typing import Any

from redis.exceptions import RedisError


class FakeRedis:
    """Values are ints; ``ttl`` holds the expiry time of keys that have one."""

    def __init__(self) -> None:
        self.values: dict[str, int] = {}
        self.ttl: dict[str, float] = {}
        self.error: RedisError | None = None

    def _check(self, key: str) -> None:
        if self.error is not None:
            raise self.error
        if key in self.ttl and self.ttl[key] <= time.time():
            self.values.pop(key, None)
            self.ttl.pop(key, None)

    def get(self, key: str) -> bytes | None:
        self._check(key)
        value = self.values.get(key)
        return None if value is None else str(value).encode()

    def incr(self, key: str) -> int:
        self._check(key)
        self.values[key] = self.values.get(key, 0) + 1
        return self.values[key]

    def expire(self, key: str, seconds: int, nx: bool = False) -> bool:
        self._check(key)
        if key not in self.values or (nx and key in self.ttl):
            return False
        self.ttl[key] = time.time() + seconds
        return True

    def delete(self, key: str) -> int:
        self._check(key)
        self.ttl.pop(key, None)
        return 1 if self.values.pop(key, None) is not None else 0

    def pipeline(self, transaction: bool = True) -> FakePipeline:
        return FakePipeline(self)


class FakePipeline:
    """Queue commands; ``execute`` runs them in order and returns their results."""

    def __init__(self, client: FakeRedis) -> None:
        self._client = client
        self._calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def incr(self, key: str) -> None:
        self._calls.append(("incr", (key,), {}))

    def expire(self, key: str, seconds: int, nx: bool = False) -> None:
        self._calls.append(("expire", (key, seconds), {"nx": nx}))

    def execute(self) -> list[Any]:
        return [getattr(self._client, name)(*a, **kw) for name, a, kw in self._calls]
