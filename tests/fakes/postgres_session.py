"""Fake SQLAlchemy ``Session`` and helpers for unit tests of ``PostgreSQLStore``.

``make_store`` patches ``postgres.Session`` so the store uses the fake and skips
engine setup, so no PostgreSQL instance is needed.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql import Delete, Select

from data.models import LegalDocument
from plugins.relational_db import postgres
from plugins.relational_db.postgres import PostgreSQLStore


class FakeResult:
    """Result of :meth:`FakeSession.execute`: at most one row."""

    def __init__(self, row: LegalDocument | None) -> None:
        self.row = row

    def scalar_one_or_none(self) -> LegalDocument | None:
        return self.row

    def scalars(self) -> FakeResult:
        return self

    def all(self) -> list[LegalDocument]:
        return [] if self.row is None else [self.row]


def _tenant_matches(sql: str, params: dict[str, Any], row: LegalDocument) -> bool:
    """Apply the tenant rule the SQL uses: strict write rule or own-or-shared read rule."""
    tenant = params.get("tenant_id_1")
    if "IS NOT DISTINCT FROM" in sql or "tenant_id" not in sql:
        return row.tenant_id == tenant
    return row.tenant_id is None or (tenant is not None and row.tenant_id == tenant)


class FakeSession:
    """Fake session: ``get`` returns *row* and records its kwargs.

    ``execute`` takes a select or delete, records its PostgreSQL SQL and bound
    params, and returns *row* only when it passes the statement filters: the
    ``id_1`` param when present, and the tenant rule the SQL uses (strict
    ``IS NOT DISTINCT FROM`` for writes, own-or-shared for reads).
    ``commit`` raises *commit_error* when set; ``add``, commits and rollbacks
    are recorded.
    """

    def __init__(self, row: LegalDocument | None, commit_error: Exception | None = None) -> None:
        self.row = row
        self.commit_error = commit_error
        self.added: list[Any] = []
        self.get_kwargs: list[dict[str, Any]] = []
        self.statements: list[str] = []
        self.params: list[dict[str, Any]] = []
        self.commits = 0
        self.rollbacks = 0

    def __enter__(self) -> FakeSession:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def get(self, _model: object, _key: str, **kwargs: Any) -> LegalDocument | None:
        self.get_kwargs.append(kwargs)
        return self.row

    def execute(self, stmt: Select[Any] | Delete) -> FakeResult:
        compiled = stmt.compile(dialect=postgresql.dialect())
        self.statements.append(str(compiled))
        params = compiled.params
        self.params.append(dict(params))
        row = self.row
        if row is None or ("id_1" in params and row.id != params["id_1"]):
            return FakeResult(None)
        return FakeResult(row if _tenant_matches(str(compiled), dict(params), row) else None)

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
