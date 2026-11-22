"""Shared fixtures for the user service unit tests."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fakes.users import TENANT, FakeLimiter, FakeRepo

from core.security import RequestPrincipal, principal_context, tenant_context
from core.users import UserService


@pytest.fixture(autouse=True)
def _fast_bcrypt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BCRYPT_ROUNDS", "4")


@pytest.fixture
def repo() -> FakeRepo:
    return FakeRepo()


@pytest.fixture
def limiter(repo: FakeRepo) -> FakeLimiter:
    """Limiter that logs its hits into ``repo.calls``, so the call order is visible."""
    return FakeLimiter(log=repo.calls)


@pytest.fixture
def service(repo: FakeRepo, limiter: FakeLimiter) -> UserService:
    return UserService(repo, limiter)


@pytest.fixture
def as_admin() -> Iterator[None]:
    with tenant_context(TENANT), principal_context(RequestPrincipal(" A@X.pl ", "admin")):
        yield
