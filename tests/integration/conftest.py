"""Shared fixtures for integration tests: PostgreSQL URL and eager Celery."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, text

from config.settings import get_settings
from tasks.celery_app import app


def can_connect(url: str) -> bool:
    """Return True when the database at the URL answers a query."""
    try:
        engine = create_engine(url, future=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return True
    except Exception:
        return False


@pytest.fixture
def postgres_url() -> str:
    """Return the configured PostgreSQL URL; skip the test when it is unreachable."""
    url = get_settings().postgres_url
    if not can_connect(url):
        pytest.skip("PostgreSQL unavailable")
    return url


@pytest.fixture
def eager_celery() -> Iterator[None]:
    """Run Celery tasks in process and raise their errors."""
    old = (app.conf.task_always_eager, app.conf.task_eager_propagates)
    app.conf.task_always_eager = True
    app.conf.task_eager_propagates = True
    yield
    app.conf.task_always_eager, app.conf.task_eager_propagates = old
