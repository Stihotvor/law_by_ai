"""Worker DB pool checks not covered by the settings, store or fetch-task tests.

Covers pool isolation between app and worker, the frozen ``PoolConfig``, store
reuse, and the pool variables in docker-compose, ``.env.example`` and the
settings docs. No Docker, no network.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
import yaml

from config import settings as settings_module
from config.settings import PoolConfig, Settings
from tasks import fetch

ROOT = Path(__file__).resolve().parents[2]


# QA-017
def test_empty_worker_values_use_defaults(clean_pool_env: pytest.MonkeyPatch) -> None:
    clean_pool_env.setenv("WORKER_POSTGRES_POOL_SIZE", "")
    clean_pool_env.setenv("WORKER_POSTGRES_MAX_OVERFLOW", "")
    assert Settings().worker_pool_config() == PoolConfig(1, 1)


# QA-018
def test_minimum_app_pool_is_accepted(clean_pool_env: pytest.MonkeyPatch) -> None:
    clean_pool_env.setenv("POSTGRES_POOL_SIZE", "1")
    clean_pool_env.setenv("POSTGRES_MAX_OVERFLOW", "0")
    assert Settings().app_pool_config() == PoolConfig(1, 0)


# QA-021
def test_pool_config_is_frozen() -> None:
    cfg = PoolConfig(1, 1)
    with pytest.raises(dataclasses.FrozenInstanceError):
        cfg.size = 0  # type: ignore[misc]
    assert cfg.size == 1


# QA-024
def test_worker_settings_do_not_change_app_pool(clean_pool_env: pytest.MonkeyPatch) -> None:
    clean_pool_env.setenv("WORKER_POSTGRES_POOL_SIZE", "1")
    clean_pool_env.setenv("POSTGRES_POOL_SIZE", "5")
    assert Settings().app_pool_config().size == 5


# QA-025
def test_app_settings_do_not_change_worker_pool(clean_pool_env: pytest.MonkeyPatch) -> None:
    clean_pool_env.setenv("POSTGRES_POOL_SIZE", "9")
    clean_pool_env.setenv("POSTGRES_MAX_OVERFLOW", "9")
    assert Settings().worker_pool_config() == PoolConfig(1, 1)


# QA-036
@pytest.mark.usefixtures("reset_store")
def test_repeated_requests_reuse_one_store(clean_pool_env: pytest.MonkeyPatch) -> None:
    factory = MagicMock(side_effect=lambda **_: MagicMock())
    clean_pool_env.setattr(fetch, "PostgreSQLStore", factory)
    first = fetch._make_store()
    assert fetch._make_store() is first
    assert fetch._make_store() is first
    factory.assert_called_once()


def _service_env(service: str) -> dict[str, Any]:
    """Return the ``environment`` mapping of a docker-compose *service*."""
    data = yaml.safe_load((ROOT / "docker" / "docker-compose.yml").read_text())
    env = data["services"][service]["environment"]
    assert isinstance(env, dict)
    return env


# QA-040
def test_compose_passes_app_pool_variables() -> None:
    env = _service_env("app")
    assert "POSTGRES_POOL_SIZE" in env
    assert "POSTGRES_MAX_OVERFLOW" in env


# QA-041
def test_compose_passes_worker_pool_variables() -> None:
    env = _service_env("celery-worker")
    assert "WORKER_POSTGRES_POOL_SIZE" in env
    assert "WORKER_POSTGRES_MAX_OVERFLOW" in env


# QA-045
def test_compose_init_gets_no_pool_variables(pool_env_names: tuple[str, ...]) -> None:
    env = _service_env("init")
    for name in pool_env_names:
        assert name not in env


# QA-043
def test_env_example_lists_pool_variables() -> None:
    lines = (ROOT / "docker" / ".env.example").read_text().splitlines()
    for line in (
        "# POSTGRES_POOL_SIZE=3",
        "# POSTGRES_MAX_OVERFLOW=2",
        "# WORKER_POSTGRES_POOL_SIZE=1",
        "# WORKER_POSTGRES_MAX_OVERFLOW=1",
    ):
        assert line in lines


# QA-044
def test_settings_docs_table_lists_pool_defaults() -> None:
    doc = settings_module.__doc__ or ""
    for name, default in (
        ("POSTGRES_POOL_SIZE", "3"),
        ("POSTGRES_MAX_OVERFLOW", "2"),
        ("WORKER_POSTGRES_POOL_SIZE", "1"),
        ("WORKER_POSTGRES_MAX_OVERFLOW", "1"),
    ):
        row = next(r for r in doc.splitlines() if r.startswith(f"``{name}``"))
        assert row.rstrip().endswith(f"``{default}``")
