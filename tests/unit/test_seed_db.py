"""Tests for the seed script's password handling."""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "seed_db.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("seed_db", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_admin_password_is_read_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEED_ADMIN_PASSWORD", "from-env")
    assert _load().admin_password() == "from-env"


def test_admin_password_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SEED_ADMIN_PASSWORD", raising=False)
    with pytest.raises(SystemExit, match="SEED_ADMIN_PASSWORD"):
        _load().admin_password()
