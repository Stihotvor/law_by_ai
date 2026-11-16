"""QA cases for worker-db-pool-size that no other unit test covers (no Docker, no network)."""

from __future__ import annotations

import dataclasses
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from config import settings as settings_module
from config.settings import PoolConfig, Settings
from plugins.relational_db import postgres
from tasks import fetch

ROOT = Path(__file__).resolve().parents[2]
NAMES = (
    "POSTGRES_POOL_SIZE",
    "POSTGRES_MAX_OVERFLOW",
    "WORKER_POSTGRES_POOL_SIZE",
    "WORKER_POSTGRES_MAX_OVERFLOW",
)


@pytest.fixture
def clean(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    monkeypatch.setattr("config.settings.load_env", lambda *a, **k: None)
    for name in NAMES:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


@pytest.fixture(autouse=True)
def reset_store() -> None:
    fetch._store = None
    yield
    fetch._store = None


@pytest.mark.parametrize(
    ("name", "attr", "value"),
    [
        ("POSTGRES_POOL_SIZE", "postgres_pool_size", 3),
        ("POSTGRES_MAX_OVERFLOW", "postgres_max_overflow", 2),
        ("WORKER_POSTGRES_POOL_SIZE", "worker_postgres_pool_size", 2),
        ("WORKER_POSTGRES_MAX_OVERFLOW", "worker_postgres_max_overflow", 0),
    ],
)
def test_qa_005_to_008_overrides(
    clean: pytest.MonkeyPatch, name: str, attr: str, value: int
) -> None:
    clean.setenv(name, str(value))
    assert getattr(Settings(), attr) == value


def test_qa_017_empty_worker_values_use_defaults(clean: pytest.MonkeyPatch) -> None:
    clean.setenv("WORKER_POSTGRES_POOL_SIZE", "")
    clean.setenv("WORKER_POSTGRES_MAX_OVERFLOW", "")
    assert Settings().worker_pool_config() == PoolConfig(1, 1)


def test_qa_018_minimum_boundary(clean: pytest.MonkeyPatch) -> None:
    clean.setenv("POSTGRES_POOL_SIZE", "1")
    clean.setenv("POSTGRES_MAX_OVERFLOW", "0")
    assert Settings().app_pool_config() == PoolConfig(1, 0)


def test_qa_021_pool_config_is_frozen() -> None:
    cfg = PoolConfig(1, 1)
    with pytest.raises(dataclasses.FrozenInstanceError):
        cfg.size = 0  # type: ignore[misc]
    assert cfg.size == 1


def test_qa_024_worker_settings_do_not_change_app_pool(clean: pytest.MonkeyPatch) -> None:
    clean.setenv("WORKER_POSTGRES_POOL_SIZE", "1")
    clean.setenv("POSTGRES_POOL_SIZE", "5")
    assert Settings().app_pool_config().size == 5


def test_qa_025_app_settings_do_not_change_worker_pool(clean: pytest.MonkeyPatch) -> None:
    clean.setenv("POSTGRES_POOL_SIZE", "9")
    clean.setenv("POSTGRES_MAX_OVERFLOW", "9")
    assert Settings().worker_pool_config() == PoolConfig(1, 1)


def test_qa_027_bad_overflow_never_unlimited(clean: pytest.MonkeyPatch) -> None:
    clean.setenv("POSTGRES_MAX_OVERFLOW", "-1")
    with pytest.raises(ValueError, match="POSTGRES_MAX_OVERFLOW"):
        Settings().app_pool_config()


def test_qa_034_failed_build_keeps_store_none(clean: pytest.MonkeyPatch) -> None:
    clean.setenv("WORKER_POSTGRES_MAX_OVERFLOW", "-1")
    clean.setattr(fetch, "PostgreSQLStore", MagicMock())
    with pytest.raises(ValueError, match="WORKER_POSTGRES_MAX_OVERFLOW"):
        fetch._make_store()
    assert fetch._store is None


def test_qa_036_repeated_requests_reuse_one_store(clean: pytest.MonkeyPatch) -> None:
    factory = MagicMock(side_effect=lambda **_: MagicMock())
    clean.setattr(fetch, "PostgreSQLStore", factory)
    first = fetch._make_store()
    assert fetch._make_store() is first
    assert fetch._make_store() is first
    factory.assert_called_once()


def _services() -> dict[str, dict[str, object]]:
    data = yaml.safe_load((ROOT / "docker" / "docker-compose.yml").read_text())
    return data["services"]


def test_qa_040_compose_app_pool_variables() -> None:
    env = _services()["app"]["environment"]
    assert "POSTGRES_POOL_SIZE" in env
    assert "POSTGRES_MAX_OVERFLOW" in env


def test_qa_041_compose_worker_pool_variables() -> None:
    env = _services()["celery-worker"]["environment"]
    assert "WORKER_POSTGRES_POOL_SIZE" in env
    assert "WORKER_POSTGRES_MAX_OVERFLOW" in env


def test_qa_045_init_has_no_pool_variables() -> None:
    env = _services()["init"]["environment"]
    for name in NAMES:
        assert name not in env


def test_qa_043_env_example_lists_four_variables() -> None:
    lines = (ROOT / "docker" / ".env.example").read_text().splitlines()
    for line in (
        "# POSTGRES_POOL_SIZE=5",
        "# POSTGRES_MAX_OVERFLOW=10",
        "# WORKER_POSTGRES_POOL_SIZE=1",
        "# WORKER_POSTGRES_MAX_OVERFLOW=1",
    ):
        assert line in lines


def test_qa_044_settings_docs_table() -> None:
    doc = settings_module.__doc__ or ""
    for name, default in (
        ("POSTGRES_POOL_SIZE", "5"),
        ("POSTGRES_MAX_OVERFLOW", "10"),
        ("WORKER_POSTGRES_POOL_SIZE", "1"),
        ("WORKER_POSTGRES_MAX_OVERFLOW", "1"),
    ):
        row = next(r for r in doc.splitlines() if r.startswith(f"``{name}``"))
        assert row.rstrip().endswith(f"``{default}``")


def test_qa_postgres_module_importable() -> None:
    assert postgres.PostgreSQLStore
