"""Fake SQLAlchemy ``Session`` and helpers for unit tests of ``PostgreSQLStore``.

``make_store`` patches ``postgres.Session`` so the store uses the fake and skips
engine setup, so no PostgreSQL instance is needed.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql import Select

from data.models import LegalDocument
from plugins.relational_db import postgres
from plugins.relational_db.postgres import PostgreSQLStore


class FakeResult:
    """Result of :meth:`FakeSession.execute`: at most one row."""

    def __init__(self, row: LegalDocument | None) -> None:
        self.row = row

    def scalar_one_or_none(self) -> LegalDocument | None:
        return self.row


class FakeSession:
    """Fake session: ``get`` returns *row* and records its kwargs.

    ``execute`` takes the ``update_document`` select (id and NULL-safe tenant
    match), records its PostgreSQL SQL and returns *row* only when it matches.
    ``commit`` raises *commit_error* when set; ``add``, commits and rollbacks
    are recorded.
    """

    def __init__(self, row: LegalDocument | None, commit_error: Exception | None = None) -> None:
        self.row = row
        self.commit_error = commit_error
        self.added: list[Any] = []
        self.get_kwargs: list[dict[str, Any]] = []
        self.statements: list[str] = []
        self.commits = 0
        self.rollbacks = 0

    def __enter__(self) -> FakeSession:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def get(self, _model: object, _key: str, **kwargs: Any) -> LegalDocument | None:
        self.get_kwargs.append(kwargs)
        return self.row

    def execute(self, stmt: Select[Any]) -> FakeResult:
        compiled = stmt.compile(dialect=postgresql.dialect())
        self.statements.append(str(compiled))
        params = compiled.params
        row = self.row
        if row is None or row.id != params.get("id_1"):
            return FakeResult(None)
        return FakeResult(row if row.tenant_id == params.get("tenant_id_1") else None)

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    def commit(self) -> None:
        if self.commit_error is not None:
            raise self.commit_error
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def make_store(monkeypatch: pytest.MonkeyPatch, session: FakeSession) -> PostgreSQLStore:
    """Return a store whose every ``Session(...)`` is *session*."""
    store = PostgreSQLStore()
    monkeypatch.setattr(store, "_ensure_initialized", lambda: None)
    monkeypatch.setattr(postgres, "Session", lambda _engine: session)
    return store


def make_doc(**extra: Any) -> dict[str, Any]:
    """Minimal ``save_document`` payload (no ``id``) plus *extra*."""
    return {"title": "t", "content": "c", "source": "s", "source_url": "u", **extra}


def store_warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    """WARNING messages logged by the ``postgres`` module."""
    return [
        r.getMessage()
        for r in caplog.records
        if r.name == postgres.__name__ and r.levelno == logging.WARNING
    ]
