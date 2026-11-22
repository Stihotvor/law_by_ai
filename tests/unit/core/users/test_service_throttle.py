"""UserService create limit per acting admin, checked against fakes (tests/fakes/users.py)."""

from __future__ import annotations

import logging

import pytest
from fakes.users import TENANT, FakeLimiter, FakeRepo
from redis.exceptions import ConnectionError as RedisConnectionError

from core.security import (
    PrincipalRequiredError,
    RequestPrincipal,
    principal_context,
    tenant_context,
)
from core.users import UserCreateRefusedError, UserCreateThrottledError, UserService

GOOD_PASSWORD = "correct-horse-1"  # noqa: S105
SHORT_PASSWORD = "short"  # noqa: S105
EMAIL = "probe-mail@x.pl"


def _create(service: UserService, email: str = EMAIL, password: str = GOOD_PASSWORD) -> None:
    service.create_user(email, password, "user", "N")


def _names(repo: FakeRepo) -> list[str]:
    return [name for name, _ in repo.calls]


@pytest.mark.usefixtures("as_admin")
def test_limiter_is_hit_after_actor_and_before_insert(
    service: UserService, repo: FakeRepo, limiter: FakeLimiter
) -> None:
    _create(service)
    assert _names(repo) == ["find_active_admin", "hit", "insert_user"]
    assert limiter.hits == ["A1"]


@pytest.mark.usefixtures("as_admin")
def test_limiter_not_hit_when_actor_is_not_an_active_admin(
    service: UserService, repo: FakeRepo, limiter: FakeLimiter
) -> None:
    repo.admin = None
    with pytest.raises(PrincipalRequiredError):
        _create(service)
    assert limiter.hits == []


def test_limiter_not_hit_for_role_user(service: UserService, limiter: FakeLimiter) -> None:
    with (
        tenant_context(TENANT),
        principal_context(RequestPrincipal("a@x.pl", "user")),
        pytest.raises(PrincipalRequiredError),
    ):
        _create(service)
    assert limiter.hits == []


@pytest.mark.parametrize("email", [EMAIL, "no-at-sign"])
@pytest.mark.usefixtures("as_admin")
def test_throttled_create_is_refused_before_input_checks(
    service: UserService, repo: FakeRepo, limiter: FakeLimiter, email: str
) -> None:
    limiter.allow = False
    with pytest.raises(UserCreateThrottledError):
        _create(service, email=email)
    assert repo.writes == []
    assert "insert_user" not in _names(repo)


@pytest.mark.usefixtures("as_admin")
def test_throttle_refusal_is_logged_with_actor_and_no_email(
    service: UserService, limiter: FakeLimiter, caplog: pytest.LogCaptureFixture
) -> None:
    limiter.allow = False
    caplog.set_level(logging.DEBUG)
    with pytest.raises(UserCreateThrottledError):
        _create(service)
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert [(r.__dict__["actor_id"], r.__dict__["error"]) for r in warnings] == [
        ("A1", "UserCreateThrottledError")
    ]
    assert warnings[0].__dict__["action"] == "create_user"
    dumped = [repr(r.__dict__) + r.getMessage() for r in caplog.records]
    assert not any("probe-mail" in text for text in dumped)


@pytest.mark.usefixtures("as_admin")
def test_invalid_input_still_counts(
    service: UserService, repo: FakeRepo, limiter: FakeLimiter
) -> None:
    with pytest.raises(UserCreateRefusedError):
        _create(service, password=SHORT_PASSWORD)
    assert limiter.hits == ["A1"]
    assert repo.writes == []


@pytest.mark.usefixtures("as_admin")
def test_deactivate_and_list_do_not_hit_the_limiter(
    service: UserService, limiter: FakeLimiter
) -> None:
    assert service.deactivate_user("U2") is True
    service.list_users()
    assert limiter.hits == []


@pytest.mark.usefixtures("as_admin")
def test_redis_error_propagates_and_nothing_is_inserted(
    service: UserService, repo: FakeRepo, limiter: FakeLimiter, caplog: pytest.LogCaptureFixture
) -> None:
    limiter.allow = RedisConnectionError("valkey down")
    with pytest.raises(RedisConnectionError):
        _create(service)
    assert repo.writes == []
    assert not [r for r in caplog.records if r.levelno == logging.WARNING]
