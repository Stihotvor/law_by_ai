"""PostgresProcedureRepository with a fake session: error mapping and the lock timeout.

The real queries run in ``tests/integration/test_procedure_repository.py``.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError

from core.procedures import Procedure, ProcedureStoreError, Step
from plugins.relational_db import procedures as module
from plugins.relational_db.procedures import PostgresProcedureRepository

SECRET = "Secret step text"  # noqa: S105 - test data


def _row(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "slug": "pesel",
        "title": "Get a PESEL",
        "schema_version": 1,
        "revision": 1,
        "key": "step-0",
        "text": SECRET,
        "source_url": "https://example.gov.pl/pesel",
        "last_checked": date(2026, 11, 1),
        "verify_with_office": "Ask the office.",
    }
    return values | overrides


def _procedure() -> Procedure:
    step = Step(
        key="step-0",
        text="One.",
        source_url="https://example.gov.pl/pesel",
        last_checked=date(2026, 11, 1),
        verify_with_office="Ask the office.",
    )
    return Procedure(schema_version=1, slug="pesel", title="Get a PESEL", steps=(step,))


class FakeSession:
    """Records executed statements; returns *rows* or raises *error* on execute."""

    def __init__(self, rows: list[dict[str, Any]], error: Exception | None = None) -> None:
        self.rows = rows
        self.error = error
        self.calls: list[str] = []

    def __call__(self, engine: object) -> FakeSession:
        return self

    def __enter__(self) -> FakeSession:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def connection(self, **kwargs: Any) -> None:
        self.calls.append("connection")

    def execute(self, stmt: Any, *args: Any) -> Any:
        self.calls.append(str(stmt))
        if self.error is not None:
            raise self.error
        return SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: self.rows))


def _repo(monkeypatch: pytest.MonkeyPatch, session: FakeSession) -> PostgresProcedureRepository:
    monkeypatch.setattr(module, "Session", session)
    return PostgresProcedureRepository(engine=object())  # type: ignore[arg-type]


def test_get_maps_an_invalid_stored_row_to_store_error(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _repo(monkeypatch, FakeSession([_row(source_url="http://plain.example/x")]))
    with pytest.raises(ProcedureStoreError) as info:
        repo.get("pesel")
    assert isinstance(info.value.__cause__, ValidationError)
    assert str(info.value) == "procedure store failed: get"
    assert SECRET not in str(info.value)


def test_get_returns_a_valid_row(monkeypatch: pytest.MonkeyPatch) -> None:
    found = _repo(monkeypatch, FakeSession([_row()])).get("pesel")
    assert found is not None
    assert found.revision == 1


def _lock_timeout() -> OperationalError:
    orig = SimpleNamespace(sqlstate="55P03")
    return OperationalError("UPDATE procedure", {}, orig)  # type: ignore[arg-type]


def test_save_sets_the_lock_timeout_first(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession([], error=_lock_timeout())
    with pytest.raises(ProcedureStoreError):
        _repo(monkeypatch, session).save(_procedure(), "a@x.org")
    assert session.calls == ["connection", "SET LOCAL lock_timeout = '5s'"]


def test_save_maps_a_lock_timeout_to_store_error(monkeypatch: pytest.MonkeyPatch) -> None:
    error = _lock_timeout()
    with pytest.raises(ProcedureStoreError) as info:
        _repo(monkeypatch, FakeSession([], error=error)).save(_procedure(), "a@x.org")
    assert info.value.__cause__ is error
    assert str(info.value) == "procedure store failed: save"
