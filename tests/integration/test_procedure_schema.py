"""Procedure knowledge base tables, grants and migration (procedure-kb T3).

Data tests run in the configured database, which the test service migrated to
head. The owner ``lawbyai_owner`` runs the DDL and CHECK tests and cleans up.
The app role ``lawbyai_app`` runs the privilege tests. The round trip and the
downgrade guard run in a scratch database. Skipped if PostgreSQL is unreachable.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from factories.scratch_db import ScratchDb, scratch_database
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
PREVIOUS_REVISION = "c4a91e7f2b58"
TABLES = ("procedure", "procedure_step", "procedure_revision")
CHECK_VIOLATION = "23514"
RESTRICT_VIOLATION = "23001"
INSUFFICIENT_PRIVILEGE = "42501"

INSERT_PROCEDURE = (
    "INSERT INTO procedure (slug, title, schema_version, revision) "
    "VALUES (:slug, :title, 1, :revision) RETURNING id"
)
INSERT_STEP = (
    "INSERT INTO procedure_step "
    "(procedure_id, position, key, text, source_url, last_checked, verify_with_office) "
    "VALUES (:pid, :position, :key, :text, :source_url, DATE '2026-11-01', :verify)"
)
INSERT_REVISION = (
    "INSERT INTO procedure_revision (procedure_id, revision, content, actor) "
    "VALUES (:pid, :revision, CAST(:content AS jsonb), :actor)"
)
TABLE_COUNT = "SELECT count(*) FROM pg_class WHERE relkind = 'r' AND relname = ANY(:names)"
CURRENT_REVISION = "SELECT version_num FROM alembic_version"


def _sqlstate(error: DBAPIError) -> str | None:
    orig = error.orig
    return getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)


def _constraint(error: DBAPIError) -> str | None:
    return getattr(getattr(error.orig, "diag", None), "constraint_name", None)


def _run(url: str, sql: str, **params: Any) -> list[tuple[Any, ...]]:
    """Run *sql* in one transaction of its own and return the rows."""
    engine = create_engine(url, future=True)
    try:
        with engine.begin() as conn:
            result = conn.execute(text(sql), params)
            return [tuple(row) for row in result.all()] if result.returns_rows else []
    finally:
        engine.dispose()


def _scalar(url: str, sql: str, **params: Any) -> Any:
    return _run(url, sql, **params)[0][0]


def _slug() -> str:
    return f"t3-{uuid.uuid4().hex[:12]}"


def _insert_procedure(url: str, slug: str) -> int:
    return int(_scalar(url, INSERT_PROCEDURE, slug=slug, title="Title", revision=1))


def _insert_revision(url: str, pid: int) -> None:
    _run(url, INSERT_REVISION, pid=pid, revision=1, content='{"slug": "x"}', actor="tester")


def _purge(owner_url: str, slug: str) -> None:
    """Remove a test procedure as the owner: revision rows first, steps cascade."""
    _run(
        owner_url,
        "DELETE FROM procedure_revision WHERE procedure_id IN "
        "(SELECT id FROM procedure WHERE slug = :slug)",
        slug=slug,
    )
    _run(owner_url, "DELETE FROM procedure WHERE slug = :slug", slug=slug)


@dataclass(frozen=True)
class Seeded:
    slug: str
    id: int


@pytest.fixture
def procedure(owner_url: str) -> Iterator[Seeded]:
    """A procedure row made by the owner; removed afterwards."""
    slug = _slug()
    pid = _insert_procedure(owner_url, slug)
    try:
        yield Seeded(slug, pid)
    finally:
        _purge(owner_url, slug)


@pytest.fixture
def with_revision(owner_url: str, procedure: Seeded) -> Seeded:
    """The procedure of ``procedure`` with one revision row."""
    _insert_revision(owner_url, procedure.id)
    return procedure


# --- CHECK constraints reject bad rows ----------------------------------------------

STEP_OK: dict[str, Any] = {
    "position": 0,
    "key": "step-one",
    "text": "Do it.",
    "source_url": "https://example.gov.pl/",
    "verify": "Ask the office.",
}
BAD_ROWS = [
    pytest.param(
        INSERT_PROCEDURE, {"title": "T", "revision": 1}, "Bad_Slug", "ck_procedure_slug", id="slug"
    ),
    pytest.param(
        INSERT_PROCEDURE, {"title": "  ", "revision": 1}, None, "ck_procedure_title", id="title"
    ),
    pytest.param(
        INSERT_PROCEDURE,
        {"title": "T", "revision": 0},
        None,
        "ck_procedure_revision_min",
        id="rev0",
    ),
    pytest.param(
        INSERT_STEP,
        {**STEP_OK, "source_url": "http://x"},
        None,
        "ck_procedure_step_source_url",
        id="http_url",
    ),
    pytest.param(
        INSERT_STEP, {**STEP_OK, "text": ""}, None, "ck_procedure_step_text", id="empty_text"
    ),
    pytest.param(
        INSERT_REVISION,
        {"revision": 1, "content": "[1, 2]", "actor": "tester"},
        None,
        "ck_procedure_revision_content",
        id="array_content",
    ),
    pytest.param(
        INSERT_REVISION,
        {"revision": 1, "content": "{}", "actor": ""},
        None,
        "ck_procedure_revision_actor",
        id="empty_actor",
    ),
]


@pytest.mark.parametrize(("sql", "params", "slug", "constraint"), BAD_ROWS)
def test_check_constraints_reject_bad_rows(
    owner_url: str,
    procedure: Seeded,
    sql: str,
    params: dict[str, Any],
    slug: str | None,
    constraint: str,
) -> None:
    """Scenario: CHECK constraints reject bad rows."""
    values = {"pid": procedure.id, "slug": slug or _slug(), **params}
    with pytest.raises(DBAPIError) as info:
        _run(owner_url, sql, **values)
    assert _sqlstate(info.value) == CHECK_VIOLATION
    assert _constraint(info.value) == constraint


def test_qa_049_051_more_check_constraints(owner_url: str, procedure: Seeded) -> None:
    """QA-049 negative position, QA-051 schema_version 0."""
    with pytest.raises(DBAPIError) as info:
        _run(owner_url, INSERT_STEP, pid=procedure.id, **{**STEP_OK, "position": -1})
    assert _sqlstate(info.value) == CHECK_VIOLATION
    version_zero = INSERT_PROCEDURE.replace(", 1, :revision", ", 0, :revision")
    with pytest.raises(DBAPIError) as info:
        _run(owner_url, version_zero, slug=_slug(), title="T", revision=1)
    assert _sqlstate(info.value) == CHECK_VIOLATION


def test_qa_050_duplicate_step_position_and_key(owner_url: str, procedure: Seeded) -> None:
    unique_violation = "23505"
    _run(owner_url, INSERT_STEP, pid=procedure.id, **STEP_OK)
    with pytest.raises(DBAPIError) as info:
        _run(owner_url, INSERT_STEP, pid=procedure.id, **{**STEP_OK, "key": "other-key"})
    assert _sqlstate(info.value) == unique_violation
    with pytest.raises(DBAPIError) as info:
        _run(owner_url, INSERT_STEP, pid=procedure.id, **{**STEP_OK, "position": 1})
    assert _sqlstate(info.value) == unique_violation


def test_qa_045_duplicate_revision_number(owner_url: str, with_revision: Seeded) -> None:
    with pytest.raises(DBAPIError) as info:
        _insert_revision(owner_url, with_revision.id)
    assert _sqlstate(info.value) == "23505"


def test_qa_042_deleting_a_procedure_cascades_steps(owner_url: str, procedure: Seeded) -> None:
    for position in range(3):
        _run(
            owner_url,
            INSERT_STEP,
            pid=procedure.id,
            **{**STEP_OK, "position": position, "key": f"step-{position}"},
        )
    _run(owner_url, "DELETE FROM procedure WHERE id = :pid", pid=procedure.id)
    count = "SELECT count(*) FROM procedure_step WHERE procedure_id = :pid"
    assert _scalar(owner_url, count, pid=procedure.id) == 0


# --- app role cannot change history ----------------------------------------------


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE procedure_revision SET actor = 'x' WHERE procedure_id = :pid",
        "DELETE FROM procedure_revision WHERE procedure_id = :pid",
        "DELETE FROM procedure WHERE id = :pid",
        "TRUNCATE procedure",
        "TRUNCATE procedure_step",
        "TRUNCATE procedure_revision",
    ],
    ids=[
        "update_revision",
        "delete_revision",
        "delete_procedure",
        "truncate_procedure",
        "truncate_step",
        "truncate_revision",
    ],
)
def test_app_role_cannot_change_history(
    postgres_url: str, owner_url: str, with_revision: Seeded, sql: str
) -> None:
    """Scenario: app role cannot change history."""
    params = {"pid": with_revision.id} if ":pid" in sql else {}
    with pytest.raises(DBAPIError) as info:
        _run(postgres_url, sql, **params)
    assert _sqlstate(info.value) == INSUFFICIENT_PRIVILEGE
    count = "SELECT count(*) FROM procedure_revision WHERE procedure_id = :pid"
    assert _scalar(owner_url, count, pid=with_revision.id) == 1


# --- app role can do its writes ---------------------------------------------------


def _app_writes(postgres_url: str, slug: str) -> int:
    """Run every write the app role needs, each as its own statement and transaction."""
    pid = _insert_procedure(postgres_url, slug)
    _run(postgres_url, "UPDATE procedure SET revision = revision + 1 WHERE id = :pid", pid=pid)
    _run(postgres_url, INSERT_STEP, pid=pid, **STEP_OK)
    _run(
        postgres_url,
        "UPDATE procedure_step SET text = 'Done.' WHERE procedure_id = :pid",
        pid=pid,
    )
    _run(postgres_url, "DELETE FROM procedure_step WHERE procedure_id = :pid", pid=pid)
    _run(postgres_url, INSERT_STEP, pid=pid, **STEP_OK)
    _insert_revision(postgres_url, pid)
    return pid


def test_app_role_can_do_its_writes(postgres_url: str, owner_url: str) -> None:
    """Scenario: app role can do its writes."""
    slug = _slug()
    try:
        pid = _app_writes(postgres_url, slug)
        sql = (
            "SELECT p.revision, count(DISTINCT s.position), count(DISTINCT r.id) "
            "FROM procedure p JOIN procedure_step s ON s.procedure_id = p.id "
            "JOIN procedure_revision r ON r.procedure_id = p.id WHERE p.id = :pid "
            "GROUP BY p.revision"
        )
        assert _run(postgres_url, sql, pid=pid) == [(2, 1, 1)]
    finally:
        _purge(owner_url, slug)


# --- revision rows block procedure delete -----------------------------------------


def test_revision_rows_block_procedure_delete(owner_url: str, with_revision: Seeded) -> None:
    """Scenario: revision rows block procedure delete."""
    with pytest.raises(DBAPIError) as info:
        _run(owner_url, "DELETE FROM procedure WHERE id = :pid", pid=with_revision.id)
    assert _sqlstate(info.value) == RESTRICT_VIOLATION
    assert _constraint(info.value) == "fk_procedure_revision_procedure_id"
    assert (
        _scalar(owner_url, "SELECT count(*) FROM procedure WHERE id = :pid", pid=with_revision.id)
        == 1
    )


# --- upgrade and downgrade (scratch database) --------------------------------------


def _alembic_config() -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    return cfg


@pytest.fixture
def scratch(postgres_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[ScratchDb]:
    """Scratch database at ``c4a91e7f2b58``, migrated by the owner; the env URLs point at it."""
    with scratch_database("migpkb") as db:
        monkeypatch.setenv("POSTGRES_URL", db.app_url)
        monkeypatch.setenv("POSTGRES_OWNER_URL", db.owner_url)
        command.upgrade(_alembic_config(), PREVIOUS_REVISION)
        yield db


def _tables(url: str) -> int:
    return int(_scalar(url, TABLE_COUNT, names=list(TABLES)))


def test_migration_round_trip(scratch: ScratchDb) -> None:
    """Scenario: migration round trip."""
    cfg = _alembic_config()
    assert _tables(scratch.app_url) == 0
    command.upgrade(cfg, "head")
    assert _tables(scratch.app_url) == len(TABLES)
    command.downgrade(cfg, "-1")
    assert _tables(scratch.app_url) == 0
    assert _scalar(scratch.app_url, CURRENT_REVISION) == PREVIOUS_REVISION


def test_downgrade_guards_history(scratch: ScratchDb) -> None:
    """Scenario: downgrade guards history."""
    cfg = _alembic_config()
    command.upgrade(cfg, "head")
    head = _scalar(scratch.app_url, CURRENT_REVISION)
    _insert_revision(scratch.owner_url, _insert_procedure(scratch.owner_url, _slug()))
    with pytest.raises(RuntimeError, match="procedure_revision holds 1 rows"):
        command.downgrade(cfg, "-1")
    assert _tables(scratch.app_url) == len(TABLES)
    assert _scalar(scratch.app_url, CURRENT_REVISION) == head
