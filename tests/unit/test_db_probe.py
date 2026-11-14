"""The integration URL fixtures skip only when the database host is unreachable.

Pure unit tests: a fake engine raises the connect error under test.
"""

from __future__ import annotations

from typing import Any

import pytest
from factories import db_probe
from sqlalchemy.exc import OperationalError

URL = "postgresql+psycopg://lawbyai_app:pw@db:5432/app"
UNREACHABLE = (
    'connection to server at "127.0.0.1", port 5432 failed: Connection refused',
    'could not translate host name "db" to address: Name or service not known',
    "failed to resolve host 'db': [Errno -3] Temporary failure in name resolution",
)
OTHER = (
    'FATAL:  password authentication failed for user "lawbyai_app"',
    'FATAL:  role "lawbyai_owner" does not exist',
)


class _Conn:
    def __enter__(self) -> _Conn:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def execute(self, *args: Any) -> None:
        return None


class _Engine:
    def __init__(self, error: str | None) -> None:
        self.error, self.disposed = error, False

    def connect(self) -> _Conn:
        if self.error is not None:
            raise OperationalError("SELECT 1", None, Exception(self.error))
        return _Conn()

    def dispose(self) -> None:
        self.disposed = True


def _patch(monkeypatch: pytest.MonkeyPatch, error: str | None) -> _Engine:
    engine = _Engine(error)
    monkeypatch.setattr(db_probe, "create_engine", lambda *_a, **_k: engine)
    return engine


def test_reachable_database_connects(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _patch(monkeypatch, None)

    assert db_probe.can_connect(URL) is True
    assert engine.disposed


@pytest.mark.parametrize("message", UNREACHABLE)
def test_unreachable_host_returns_false(monkeypatch: pytest.MonkeyPatch, message: str) -> None:
    engine = _patch(monkeypatch, message)

    assert db_probe.can_connect(URL) is False
    assert engine.disposed


@pytest.mark.parametrize("message", OTHER)
def test_auth_or_role_error_fails(monkeypatch: pytest.MonkeyPatch, message: str) -> None:
    engine = _patch(monkeypatch, message)

    with pytest.raises(OperationalError, match=message.split(":  ", 1)[1][:20]):
        db_probe.can_connect(URL)
    assert engine.disposed


def test_non_operational_error_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _Engine(None)
    monkeypatch.setattr(engine, "connect", lambda: (_ for _ in ()).throw(ValueError("bad")))
    monkeypatch.setattr(db_probe, "create_engine", lambda *_a, **_k: engine)

    with pytest.raises(ValueError, match="bad"):
        db_probe.can_connect(URL)
    assert engine.disposed
