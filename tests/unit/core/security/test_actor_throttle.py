"""Per-actor create limit against a hand-written Redis fake (tests/fakes/valkey.py)."""

from __future__ import annotations

import time

import pytest
from fakes.valkey import FakeRedis
from redis.exceptions import ConnectionError as RedisConnectionError

from core.security.actor_throttle import ActorThrottle

PREFIX = "user:create:"
ACTOR = "a-1"
MAX = 3
WINDOW = 3600


def _throttle(client: FakeRedis) -> ActorThrottle:
    return ActorThrottle(client, MAX, WINDOW, PREFIX)


def test_hits_up_to_max_pass_and_the_next_is_refused() -> None:
    t = _throttle(FakeRedis())
    assert [t.hit(ACTOR) for _ in range(MAX + 1)] == [True, True, True, False]


def test_key_is_prefix_and_actor_id_only() -> None:
    client = FakeRedis()
    _throttle(client).hit(ACTOR)
    assert list(client.values) == [f"{PREFIX}{ACTOR}"]
    assert not any("@" in key for key in client.values)


def test_ttl_is_set_only_on_the_first_hit() -> None:
    client = FakeRedis()
    t = _throttle(client)
    t.hit(ACTOR)
    first = client.ttl[f"{PREFIX}{ACTOR}"]
    assert 0 < first - time.time() <= WINDOW
    client.ttl[f"{PREFIX}{ACTOR}"] = first - 10
    t.hit(ACTOR)
    assert client.ttl[f"{PREFIX}{ACTOR}"] == first - 10


def test_actors_are_counted_separately() -> None:
    client = FakeRedis()
    t = _throttle(client)
    for _ in range(MAX + 1):
        t.hit(ACTOR)
    assert t.hit("a-2") is True
    assert client.values == {f"{PREFIX}{ACTOR}": MAX + 1, f"{PREFIX}a-2": 1}


def test_redis_error_propagates() -> None:
    client = FakeRedis()
    client.error = RedisConnectionError("down")
    with pytest.raises(RedisConnectionError):
        _throttle(client).hit(ACTOR)
