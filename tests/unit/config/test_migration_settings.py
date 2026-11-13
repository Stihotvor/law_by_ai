"""Migrations use the owner URL: Alembic env.py and the compose services (rls-201 T2)."""

from __future__ import annotations

import io
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml
from alembic.config import Config
from alembic.runtime.environment import EnvironmentContext
from alembic.script import ScriptDirectory

from config.settings import get_settings

ROOT = Path(__file__).resolve().parents[3]
COMPOSE = ROOT / "docker" / "docker-compose.yml"
OWNER_VAR = "LAWBYAI_OWNER_PASSWORD"
APP_VAR = "LAWBYAI_APP_PASSWORD"
UPGRADE = "alembic upgrade head"


@pytest.fixture
def owner_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Set the owner and app variables; clear the URL overrides and the settings cache."""
    for key in ("POSTGRES_URL", "POSTGRES_OWNER_URL"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv(OWNER_VAR, "own%er@pw")  # % must survive configparser
    monkeypatch.setenv(APP_VAR, "app-pw")
    monkeypatch.setenv("POSTGRES_HOST", "db")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _run_env_py(url: str = "") -> Config:
    """Run migrations/env.py in offline mode with no revisions to apply."""
    cfg = Config(output_buffer=io.StringIO())
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    script = ScriptDirectory.from_config(cfg)
    with EnvironmentContext(cfg, script, fn=lambda _rev, _ctx: [], as_sql=True):
        script.run_env()
    return cfg


def test_settings_alembic_uses_the_owner_url(owner_env: None) -> None:
    """Scenario: Alembic uses the owner URL."""
    cfg = _run_env_py()

    url = cfg.get_main_option("sqlalchemy.url")
    assert url == get_settings().postgres_owner_url
    assert url is not None
    assert "lawbyai_owner" in url


def test_settings_alembic_keeps_a_url_the_caller_set(owner_env: None) -> None:
    """A URL already on the Alembic config wins over the settings."""
    cfg = _run_env_py("postgresql://lawbyai_owner:p%%40ss@other/x")

    assert cfg.get_main_option("sqlalchemy.url") == "postgresql://lawbyai_owner:p%40ss@other/x"


def _services() -> dict[str, Any]:
    """Return the parsed compose services."""
    return yaml.safe_load(COMPOSE.read_text())["services"]


def _command_text(service: dict[str, Any]) -> str:
    """Return the service command as one string."""
    command = service["command"]
    return command if isinstance(command, str) else " ".join(command)


@pytest.mark.parametrize(("name", "main"), [("init", "python -m bootstrap"), ("test", "pytest")])
def test_settings_compose_migrates_with_the_owner(name: str, main: str) -> None:
    """Scenario: Compose migrates with the owner."""
    service = _services()[name]
    command = _command_text(service)
    env = service["environment"]

    assert UPGRADE in command
    assert main in command
    assert command.index(UPGRADE) < command.index(main)
    assert OWNER_VAR in env
    assert APP_VAR in env


def test_settings_compose_owner_url_override_is_blank() -> None:
    """The test service blanks POSTGRES_OWNER_URL from its env file; init never sets it."""
    services = _services()
    # A blank override falls back to the owner URL built from the owner password.
    assert services["test"]["environment"]["POSTGRES_OWNER_URL"] == ""
    assert "POSTGRES_OWNER_URL" not in services["init"]["environment"]


def test_settings_compose_keeps_owner_and_superuser_secrets_off_the_app() -> None:
    """The app and the worker get the app password only."""
    services = _services()
    for name in ("app", "celery-worker"):
        env = services[name]["environment"]
        assert APP_VAR in env, name
        for secret in (OWNER_VAR, "POSTGRES_USER", "POSTGRES_PASSWORD"):
            assert secret not in env, f"{name}: {secret}"
    assert "POSTGRES_PASSWORD" not in services["init"]["environment"]
