"""Worker store builder ``_make_store`` uses the worker pool (T3).

Unit tests: ``PostgreSQLStore`` is mocked, so no database or network is needed.
"""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agents.fetch.errors import InvalidReferenceError
from config.settings import PoolConfig
from tasks import fetch
from tasks.celery_app import FETCH_DOCUMENT, app

pytestmark = pytest.mark.usefixtures("reset_store")

POOL_SIZE = "WORKER_POSTGRES_POOL_SIZE"
MAX_OVERFLOW = "WORKER_POSTGRES_MAX_OVERFLOW"


@pytest.fixture
def factory(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    mock = MagicMock(side_effect=lambda **_: MagicMock())
    monkeypatch.setattr(fetch, "PostgreSQLStore", mock)
    return mock


@pytest.fixture
def invalid_agent(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Agent whose ``make_ref`` rejects every id, so the task touches no store method."""
    agent = MagicMock()
    agent.make_ref.side_effect = InvalidReferenceError("bad id")
    monkeypatch.setattr(fetch, "_make_agent", lambda _rejection: agent)
    return agent


def _store_calls_outside_make_store(tree: ast.Module) -> list[int]:
    """Return line numbers of ``PostgreSQLStore(`` calls outside ``_make_store``."""
    inside: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_make_store":
            inside.update(id(n) for n in ast.walk(node))
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "PostgreSQLStore"
        and id(node) not in inside
    ]


def test_store_receives_worker_pool(factory: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(POOL_SIZE, "1")
    monkeypatch.setenv(MAX_OVERFLOW, "1")

    fetch._make_store()

    factory.assert_called_once_with(pool=PoolConfig(1, 1))


def test_bad_worker_value_raises_and_leaves_store_none(
    factory: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(POOL_SIZE, "0")

    with pytest.raises(ValueError, match=POOL_SIZE):
        fetch._make_store()

    factory.assert_not_called()
    assert fetch._store is None


def test_retry_after_bad_value(
    factory: MagicMock, invalid_agent: MagicMock, clean_pool_env: pytest.MonkeyPatch
) -> None:
    monkeypatch = clean_pool_env
    monkeypatch.setenv(POOL_SIZE, "0")
    with pytest.raises(ValueError, match=POOL_SIZE):
        fetch._make_store()

    monkeypatch.setenv(POOL_SIZE, "1")
    result = app.tasks[FETCH_DOCUMENT].run("fake", "x")

    assert result == {"status": "invalid", "external_id": "x"}
    assert fetch._store is not None
    factory.assert_called_with(pool=PoolConfig(1, 1))


def test_task_gets_store_from_make_store(
    invalid_agent: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_store = MagicMock()
    monkeypatch.setattr(fetch, "_make_store", make_store)

    app.tasks[FETCH_DOCUMENT].run("fake", "x")

    make_store.assert_called_once_with()


def test_only_make_store_builds_the_store() -> None:
    tree = ast.parse(Path(fetch.__file__).read_text())

    assert _store_calls_outside_make_store(tree) == []
