"""PostgresProcedureRepository with fake sessions: save flow, reads, error mapping, lock timeout.

The real queries run in ``tests/integration/test_procedure_repository.py``.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import OperationalError

from core.procedures import ImportResult, Procedure, ProcedureStoreError, ProcedureSummary, Step
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


# --- Scripted session: one canned result per executed statement -------------


class Result:
    """A stand-in for a SQLAlchemy ``Result`` holding one canned value."""

    def __init__(self, value: Any = None) -> None:
        self.value = value

    def one(self) -> Any:
        return self.value

    def scalar_one(self) -> Any:
        return self.value

    def scalar_one_or_none(self) -> Any:
        return self.value

    def all(self) -> Any:
        return self.value


class ScriptedSession:
    """Returns the next scripted result per ``execute``; records statements and the outcome."""

    def __init__(self, results: list[Result], fail_at: int | None = None) -> None:
        self.results = list(results)
        self.fail_at = fail_at
        self.statements: list[Any] = []
        self.params: list[tuple[Any, ...]] = []
        self.isolation: dict[str, Any] | None = None
        self.outcome: str | None = None

    def __call__(self, engine: object) -> ScriptedSession:
        return self

    def __enter__(self) -> ScriptedSession:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def connection(self, execution_options: dict[str, Any]) -> None:
        self.isolation = execution_options

    def execute(self, stmt: Any, *args: Any) -> Result:
        if self.fail_at == len(self.statements):
            self.statements.append(stmt)
            raise _lock_timeout()
        self.statements.append(stmt)
        self.params.append(args)
        return self.results.pop(0) if self.results else Result()

    def commit(self) -> None:
        self.outcome = "commit"

    def rollback(self) -> None:
        self.outcome = "rollback"

    def sql(self) -> list[str]:
        return [str(stmt.compile(dialect=postgresql.dialect())) for stmt in self.statements]


def _locked(revision: int, procedure_id: int = 7) -> Result:
    return Result(SimpleNamespace(id=procedure_id, revision=revision))


def _scripted_repo(
    monkeypatch: pytest.MonkeyPatch, session: ScriptedSession
) -> PostgresProcedureRepository:
    monkeypatch.setattr(module, "Session", session)
    return PostgresProcedureRepository(engine=object())  # type: ignore[arg-type]


def test_save_new_procedure_writes_revision_one_and_commits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = ScriptedSession([Result(), _locked(1), Result(None), Result(), Result(), Result(1)])
    result = _scripted_repo(monkeypatch, session).save(_procedure(), "a@x.org")

    assert result == ImportResult(slug="pesel", revision=1, changed=True)
    assert session.outcome == "commit"
    assert session.isolation == {"isolation_level": "READ COMMITTED"}
    sql = session.sql()
    assert sql[0] == "SET LOCAL lock_timeout = '5s'"
    assert "ON CONFLICT (slug) DO UPDATE SET slug = excluded.slug" in sql[1]
    assert "RETURNING procedure.id, procedure.revision" in sql[1]
    assert sql[3].startswith("DELETE FROM procedure_step")
    assert sql[4].startswith("INSERT INTO procedure_step")
    assert sql[5].startswith("UPDATE procedure SET")
    assert sql[6].startswith("INSERT INTO procedure_revision")
    assert len(sql) == 7


def test_save_new_procedure_keeps_revision_one(monkeypatch: pytest.MonkeyPatch) -> None:
    session = ScriptedSession([Result(), _locked(1), Result(None), Result(), Result(), Result(1)])
    _scripted_repo(monkeypatch, session).save(_procedure(), "a@x.org")

    update_stmt = session.statements[5].compile(dialect=postgresql.dialect())
    assert "revision=%(revision)s" in str(update_stmt)
    assert update_stmt.params["revision"] == 1


def test_save_inserts_steps_by_position(monkeypatch: pytest.MonkeyPatch) -> None:
    session = ScriptedSession([Result(), _locked(1), Result(None), Result(), Result(), Result(1)])
    _scripted_repo(monkeypatch, session).save(_procedure(), "a@x.org")

    (rows,) = session.params[4]
    assert rows == [
        {
            "procedure_id": 7,
            "position": 0,
            "key": "step-0",
            "text": "One.",
            "source_url": "https://example.gov.pl/pesel",
            "last_checked": date(2026, 11, 1),
            "verify_with_office": "Ask the office.",
        }
    ]


def test_save_writes_the_revision_row_with_actor_and_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = ScriptedSession([Result(), _locked(1), Result(None), Result(), Result(), Result(1)])
    _scripted_repo(monkeypatch, session).save(_procedure(), "a@x.org")

    params = session.statements[6].compile(dialect=postgresql.dialect()).params
    assert params["procedure_id"] == 7
    assert params["revision"] == 1
    assert params["actor"] == "a@x.org"
    assert params["content"] == _procedure().model_dump(mode="json", exclude={"revision"})


def test_save_identical_content_rolls_back_without_writing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = ScriptedSession([Result(), _locked(3), Result(True)])
    result = _scripted_repo(monkeypatch, session).save(_procedure(), "a@x.org")

    assert result == ImportResult(slug="pesel", revision=3, changed=False)
    assert session.outcome == "rollback"
    assert len(session.statements) == 3
    assert "procedure_revision.content = CAST(" in session.sql()[2]


def test_save_changed_content_bumps_the_revision(monkeypatch: pytest.MonkeyPatch) -> None:
    session = ScriptedSession([Result(), _locked(3), Result(False), Result(), Result(), Result(4)])
    result = _scripted_repo(monkeypatch, session).save(_procedure(), "a@x.org")

    assert result == ImportResult(slug="pesel", revision=4, changed=True)
    assert session.outcome == "commit"
    update_sql = session.sql()[5]
    assert "revision=(procedure.revision + %(revision_1)s" in update_sql
    assert session.statements[6].compile(dialect=postgresql.dialect()).params["revision"] == 4


@pytest.mark.parametrize("fail_at", [1, 2, 3, 4, 5, 6])
def test_save_failure_at_any_step_maps_to_store_error_without_commit(
    monkeypatch: pytest.MonkeyPatch, fail_at: int
) -> None:
    session = ScriptedSession(
        [Result(), _locked(3), Result(False), Result(), Result(), Result(4)], fail_at=fail_at
    )
    with pytest.raises(ProcedureStoreError) as info:
        _scripted_repo(monkeypatch, session).save(_procedure(), "a@x.org")

    assert isinstance(info.value.__cause__, OperationalError)
    assert str(info.value) == "procedure store failed: save"
    assert session.outcome is None


def test_get_returns_none_when_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _repo(monkeypatch, FakeSession([])).get("missing") is None


def test_get_orders_steps_by_position(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [_row(key="a", revision=2), _row(key="b", revision=2)]
    found = _repo(monkeypatch, FakeSession(rows)).get("pesel")

    assert found is not None
    assert [step.key for step in found.steps] == ["a", "b"]
    assert (found.slug, found.title, found.revision) == ("pesel", "Get a PESEL", 2)


def test_get_maps_a_database_error_to_store_error(monkeypatch: pytest.MonkeyPatch) -> None:
    error = _lock_timeout()
    with pytest.raises(ProcedureStoreError) as info:
        _repo(monkeypatch, FakeSession([], error=error)).get("pesel")
    assert info.value.__cause__ is error
    assert str(info.value) == "procedure store failed: get"


def test_list_returns_summaries_sorted_by_slug(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [SimpleNamespace(slug="a", title="A"), SimpleNamespace(slug="b", title="B")]
    session = ScriptedSession([Result(rows)])
    summaries = _scripted_repo(monkeypatch, session).list()

    assert summaries == [
        ProcedureSummary(slug="a", title="A"),
        ProcedureSummary(slug="b", title="B"),
    ]
    assert session.sql()[0].endswith("ORDER BY procedure.slug")


def test_list_returns_an_empty_list(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _scripted_repo(monkeypatch, ScriptedSession([Result([])])).list() == []


def test_list_maps_a_database_error_to_store_error(monkeypatch: pytest.MonkeyPatch) -> None:
    session = ScriptedSession([], fail_at=0)
    with pytest.raises(ProcedureStoreError) as info:
        _scripted_repo(monkeypatch, session).list()
    assert isinstance(info.value.__cause__, OperationalError)
    assert str(info.value) == "procedure store failed: list"
