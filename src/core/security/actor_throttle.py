"""Per-actor attempt limit in Redis (for example new users per acting admin).

One key per actor: ``<prefix><actor_id>``. The key holds the attempt count; the first
attempt starts the window. No email and no hash in the key. No Streamlit imports.
Every Redis call may raise ``RedisError``; the caller decides how to fail.
"""

from __future__ import annotations

from .login_throttle import RedisClient

__all__ = ["ActorThrottle"]


class ActorThrottle:
    """Fixed-window counter per actor. Numbers must be positive (``Settings`` validates them)."""

    def __init__(self, client: RedisClient, max_hits: int, window_s: int, prefix: str) -> None:
        """Keep the client, the limits and the key prefix."""
        self._client = client
        self._max = max_hits
        self._window = window_s
        self._prefix = prefix

    def hit(self, actor_id: str) -> bool:
        """Count one attempt of *actor_id*; return False when the count is above the limit."""
        key = f"{self._prefix}{actor_id}"
        pipe = self._client.pipeline(transaction=True)
        pipe.incr(key)
        pipe.expire(key, self._window, nx=True)
        count = int(pipe.execute()[0])
        return count <= self._max
