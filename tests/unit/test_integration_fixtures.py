"""Integration fixtures: superuser only for CREATE/DROP DATABASE, no empty tenant.

Pure unit tests: a fake engine records each statement by user name.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from factories import scratch_db
from sqlalchemy import make_url

INTEGRATION = Path(__file__).resolve().parents[1] / "integration"
INIT_SCRIPT = Path(__file__).resolve().parents[2] / "docker" / "initdb" / "00-roles.sh"
EMPTY_TENANT = re.compile(r"set_config\(\s*'app\.current_tenant'\s*,\s*''")


class _Conn:
    def __init__(self, log: list[tuple[str, str]], user: str) -> None:
        self.log, self.user = log, user

    def __enter__(self) -> _Conn:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def execute(self, statement: Any, *args: Any) -> None:
        self.log.append((self.user, str(statement)))


class _Engine:
    def __init__(self, log: list[tuple[str, str]], url: str) -> None:
        self.log, self.user = log, make_url(url).username or ""

    def connect(self) -> _Conn:
        return _Conn(self.log, self.user)

    def dispose(self) -> None:
        return None


@pytest.fixture
def log(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """Point the scratch module at fake engines and return the statement log."""
    monkeypatch.setenv("POSTGRES_USER", "boot-su")
    monkeypatch.setenv("POSTGRES_PASSWORD", "su-pw")
    monkeypatch.setenv("LAWBYAI_OWNER_PASSWORD", "owner-pw")
    monkeypatch.setenv("LAWBYAI_APP_PASSWORD", "app-pw")
    monkeypatch.delenv("POSTGRES_URL", raising=False)
    monkeypatch.delenv("POSTGRES_OWNER_URL", raising=False)
    records: list[tuple[str, str]] = []
    monkeypatch.setattr(scratch_db, "create_engine", lambda url, **_: _Engine(records, str(url)))
    return records


def test_superuser_url_uses_bootstrap_credentials(log: list[tuple[str, str]]) -> None:
    url = make_url(scratch_db.superuser_url())

    assert (url.username, url.password) == ("boot-su", "su-pw")


def test_superuser_runs_only_create_and_drop_database(log: list[tuple[str, str]]) -> None:
    with scratch_db.scratch_database("unit") as db:
        assert make_url(db.app_url).username == "lawbyai_app"
        assert make_url(db.owner_url).username == "lawbyai_owner"
        assert make_url(db.app_url).database == db.name

    superuser = [sql for user, sql in log if user == "boot-su"]
    assert len(superuser) == 2
    assert superuser[0].startswith(f'CREATE DATABASE "{db.name}" OWNER lawbyai_owner')
    assert superuser[1].startswith(f'DROP DATABASE IF EXISTS "{db.name}"')
    assert {user for user, _ in log} == {"boot-su", "lawbyai_owner"}


def test_integration_tests_never_set_an_empty_tenant() -> None:
    found = [
        path.name
        for path in INTEGRATION.rglob("*.py")
        if EMPTY_TENANT.search(path.read_text(encoding="utf-8"))
    ]

    assert found == []


def test_scratch_schema_grant_matches_the_init_script() -> None:
    """AUTH_SCHEMA_GRANT copies one grant of the init script; it must stay the same."""
    lines = [line.strip() for line in INIT_SCRIPT.read_text().splitlines()]
    grants = [line for line in lines if line.startswith("GRANT") and "lawbyai_auth;" in line]

    assert grants == [f"{scratch_db.AUTH_SCHEMA_GRANT};"]
