"""Shared fixtures for the unit tests."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

# Env variables that size the app and worker PostgreSQL pools.
POOL_ENV_NAMES: tuple[str, ...] = (
    "POSTGRES_POOL_SIZE",
    "POSTGRES_MAX_OVERFLOW",
    "WORKER_POSTGRES_POOL_SIZE",
    "WORKER_POSTGRES_MAX_OVERFLOW",
)


@pytest.fixture
def pool_env_names() -> tuple[str, ...]:
    """Names of the four pool env variables."""
    return POOL_ENV_NAMES


@pytest.fixture
def clean_pool_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """No local env file and no pool variables; returns the monkeypatch to set them."""
    monkeypatch.setattr("config.settings.load_env", lambda *a, **k: None)
    for name in POOL_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


@pytest.fixture
def reset_store() -> Iterator[None]:
    """Empty the cached worker store before and after the test."""
    # Imported here so unit tests that do not use it never import the fetch task.
    from tasks import fetch

    fetch._store = None
    yield
    fetch._store = None
