"""PostgresProcedureRepository against the procedure tables (procedure-kb T4).

Tests connect as ``lawbyai_app``. The owner ``lawbyai_owner`` reads history,
plants a conflicting revision row and removes the test procedures (the app role
has no DELETE on ``procedure``). The empty-database scenario runs in a scratch
database at head. Skipped if PostgreSQL is unreachable.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable, Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from factories.scratch_db import scratch_database
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.exc import IntegrityError

from core.procedures import ImportResult, Procedure, ProcedureStoreError, ProcedureSummary, Step
from plugins.relational_db.procedures import PostgresProcedureRepository

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
ACTOR = "admin@example.com"
OTHER_ACTOR = "other-admin@example.com"
READ_BOUND_SECONDS = 0.1
REVISIONS_SQL = (
    "SELECT r.revision, r.actor, r.content FROM procedure_revision r "
    "JOIN procedure p ON p.id = r.procedure_id WHERE p.slug = :slug ORDER BY r.revision"
)
PROCEDURE_ROW_SQL = "SELECT id, revision, updated_at FROM procedure WHERE slug = :slug"
PLANT_REVISION_SQL = (
    "INSERT INTO procedure_revision (procedure_id, revision, content, actor) "
    "VALUES (:pid, :revision, CAST('{\"planted\": true}' AS jsonb), 'planter')"
)

SaveFn = Callable[[Procedure], ImportResult]


def _run(url: str, sql: str, **params: Any) -> list[tuple[Any, ...]]:
    """Run *sql* in one transaction of its own and return the rows."""
    engine = create_engine(url, future=True)
    try:
        with engine.begin() as conn:
            result = conn.execute(text(sql), params)
            return [tuple(row) for row in result.all()] if result.returns_rows else []
    finally:
        engine.dispose()


def _new_slug() -> str:
    return f"t4-{uuid.uuid4().hex[:12]}"


def _procedure(
    slug: str, title: str = "Get a PESEL", texts: tuple[str, ...] = ("One.",)
) -> Procedure:
    steps = tuple(
        Step(
            key=f"step-{index}",
            text=step_text,
            source_url="https://example.gov.pl/pesel",
            last_checked=date(2026, 11, 1),
            verify_with_office="Ask the municipal office.",
        )
        for index, step_text in enumerate(texts)
    )
    return Procedure(schema_version=1, slug=slug, title=title, steps=steps)


def _snapshot(procedure: Procedure) -> dict[str, Any]:
    return procedure.model_dump(mode="json", exclude={"revision"})


def _at(procedure: Procedure, revision: int) -> Procedure:
    return procedure.model_copy(update={"revision": revision})


class Slugs:
    """Hands out unique slugs and removes their rows as the owner afterwards."""

    def __init__(self, owner_url: str) -> None:
        self._owner_url = owner_url
        self._made: list[str] = []

    def new(self) -> str:
        return self.track(_new_slug())

    def track(self, slug: str) -> str:
        self._made.append(slug)
        return slug

    def purge(self) -> None:
        for slug in self._made:
            _run(
                self._owner_url,
                "DELETE FROM procedure_revision WHERE procedure_id IN "
                "(SELECT id FROM procedure WHERE slug = :slug)",
                slug=slug,
            )
            _run(self._owner_url, "DELETE FROM procedure WHERE slug = :slug", slug=slug)


@pytest.fixture
def slugs(owner_url: str) -> Iterator[Slugs]:
    made = Slugs(owner_url)
    try:
        yield made
    finally:
        made.purge()


@pytest.fixture
def app_engine(postgres_url: str) -> Iterator[Engine]:
    engine = create_engine(postgres_url, future=True)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def repo(app_engine: Engine) -> PostgresProcedureRepository:
    return PostgresProcedureRepository(app_engine)


# --- first save --------------------------------------------------------------------


def test_first_save_is_revision_one(
    repo: PostgresProcedureRepository, slugs: Slugs, owner_url: str
) -> None:
    """Scenario: first save."""
    procedure = _procedure(slugs.new())
    result = repo.save(procedure, ACTOR)
    assert result == ImportResult(slug=procedure.slug, revision=1, changed=True)
    rows = _run(owner_url, REVISIONS_SQL, slug=procedure.slug)
    assert rows == [(1, ACTOR, _snapshot(procedure))]
    assert "revision" not in rows[0][2]
    assert repo.get(procedure.slug) == _at(procedure, 1)


# --- identical content -------------------------------------------------------------


def test_identical_content_writes_nothing(
    repo: PostgresProcedureRepository, slugs: Slugs, owner_url: str
) -> None:
    """Scenario: identical content."""
    procedure = _procedure(slugs.new())
    repo.save(procedure, ACTOR)
    before = _run(owner_url, PROCEDURE_ROW_SQL, slug=procedure.slug)
    result = repo.save(procedure, OTHER_ACTOR)
    assert result == ImportResult(slug=procedure.slug, revision=1, changed=False)
    assert _run(owner_url, PROCEDURE_ROW_SQL, slug=procedure.slug) == before
    assert [row[:2] for row in _run(owner_url, REVISIONS_SQL, slug=procedure.slug)] == [(1, ACTOR)]


# --- changed content ---------------------------------------------------------------


def test_changed_content_is_next_revision(
    repo: PostgresProcedureRepository, slugs: Slugs, owner_url: str
) -> None:
    """Scenario: changed content."""
    slug = slugs.new()
    first = _procedure(slug, texts=("One.", "Two."))
    changed = _procedure(slug, texts=("One, changed.",))
    repo.save(first, ACTOR)
    result = repo.save(changed, OTHER_ACTOR)
    assert result == ImportResult(slug=slug, revision=2, changed=True)
    assert repo.get(slug) == _at(changed, 2)
    rows = _run(owner_url, REVISIONS_SQL, slug=slug)
    assert rows == [(1, ACTOR, _snapshot(first)), (2, OTHER_ACTOR, _snapshot(changed))]
    assert _run(owner_url, PROCEDURE_ROW_SQL, slug=slug)[0][1] == 2


# --- failed save keeps old data ----------------------------------------------------


def _bad_step_procedure(slug: str) -> Procedure:
    """A procedure whose step breaks ``ck_procedure_step_source_url`` (pydantic bypassed)."""
    good = _procedure(slug, title="Secret title", texts=("Secret step text.",))
    bad_step = Step.model_construct(**{**good.steps[0].model_dump(), "source_url": "http://x"})
    return Procedure.model_construct(**{**good.model_dump(), "steps": (bad_step,)})


def test_failed_save_keeps_old_data(
    repo: PostgresProcedureRepository, slugs: Slugs, owner_url: str
) -> None:
    """Scenario: failed save keeps old data."""
    slug = slugs.new()
    old = _procedure(slug)
    repo.save(old, ACTOR)
    with pytest.raises(ProcedureStoreError) as info:
        repo.save(_bad_step_procedure(slug), OTHER_ACTOR)
    assert isinstance(info.value.__cause__, IntegrityError)
    message = str(info.value)
    assert "Secret" not in message
    assert "http://x" not in message
    assert repo.get(slug) == _at(old, 1)
    assert len(_run(owner_url, REVISIONS_SQL, slug=slug)) == 1


def test_revision_conflict_maps_to_store_error(
    repo: PostgresProcedureRepository, slugs: Slugs, owner_url: str
) -> None:
    """A UNIQUE(procedure_id, revision) IntegrityError maps to ProcedureStoreError."""
    slug = slugs.new()
    old = _procedure(slug)
    repo.save(old, ACTOR)
    pid = _run(owner_url, PROCEDURE_ROW_SQL, slug=slug)[0][0]
    _run(owner_url, PLANT_REVISION_SQL, pid=pid, revision=2)
    new = _procedure(slug, title="Secret title", texts=("Secret step text.",))
    with pytest.raises(ProcedureStoreError) as info:
        repo.save(new, OTHER_ACTOR)
    cause = info.value.__cause__
    assert isinstance(cause, IntegrityError)
    assert "uq_procedure_revision_procedure_id_revision" in str(cause)
    message = str(info.value)
    for secret in ("Secret", OTHER_ACTOR, slug):
        assert secret not in message
    assert repo.get(slug) == _at(old, 1)


# --- concurrent saves --------------------------------------------------------------


def _save_together(
    repo: PostgresProcedureRepository, procedures: list[Procedure]
) -> list[ImportResult | BaseException]:
    """Run one save per procedure, each in its own thread, released at once."""
    barrier = threading.Barrier(len(procedures))
    outcomes: list[ImportResult | BaseException] = []
    lock = threading.Lock()

    def work(procedure: Procedure) -> None:
        barrier.wait()
        try:
            outcome: ImportResult | BaseException = repo.save(procedure, ACTOR)
        except BaseException as error:
            outcome = error
        with lock:
            outcomes.append(outcome)

    threads = [threading.Thread(target=work, args=(p,)) for p in procedures]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    return outcomes


@pytest.mark.parametrize("existing", [False, True], ids=["new_slug", "existing_slug"])
def test_concurrent_saves_get_consecutive_revisions(
    repo: PostgresProcedureRepository, slugs: Slugs, owner_url: str, existing: bool
) -> None:
    """Scenario: concurrent saves."""
    slug = slugs.new()
    base = 0
    if existing:
        repo.save(_procedure(slug, texts=("Base.",)), ACTOR)
        base = 1
    contenders = [_procedure(slug, texts=("Thread A.",)), _procedure(slug, texts=("Thread B.",))]
    outcomes = _save_together(repo, contenders)
    errors = [o for o in outcomes if isinstance(o, BaseException)]
    assert errors == []
    revisions = sorted(o.revision for o in outcomes if isinstance(o, ImportResult))
    assert revisions == [base + 1, base + 2]
    rows = _run(owner_url, REVISIONS_SQL, slug=slug)
    assert [row[0] for row in rows] == list(range(1, base + 3))
    current = repo.get(slug)
    assert current is not None
    assert current.revision == base + 2
    assert _snapshot(current) == rows[-1][2]


# --- not found and empty -----------------------------------------------------------


def _alembic_config() -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    return cfg


@pytest.fixture
def empty_repo(
    postgres_url: str, monkeypatch: pytest.MonkeyPatch
) -> Iterator[PostgresProcedureRepository]:
    """A repository on an empty scratch database migrated to head by the owner."""
    with scratch_database("t4pkb") as db:
        monkeypatch.setenv("POSTGRES_URL", db.app_url)
        monkeypatch.setenv("POSTGRES_OWNER_URL", db.owner_url)
        command.upgrade(_alembic_config(), "head")
        engine = create_engine(db.app_url, future=True)
        try:
            yield PostgresProcedureRepository(engine)
        finally:
            engine.dispose()


def test_not_found_and_empty(empty_repo: PostgresProcedureRepository) -> None:
    """Scenario: not found and empty."""
    assert empty_repo.get("nope") is None
    assert empty_repo.list() == []


def test_unknown_slug_is_none(repo: PostgresProcedureRepository) -> None:
    assert repo.get(_new_slug()) is None


# --- list --------------------------------------------------------------------------


def test_list_is_sorted_by_slug(repo: PostgresProcedureRepository, slugs: Slugs) -> None:
    """``list()`` returns summaries sorted by slug."""
    stem = _new_slug()
    for suffix, title in (("-c", "Third"), ("-a", "First"), ("-b", "Second")):
        repo.save(_procedure(slugs.track(stem + suffix), title=title), ACTOR)
    listed = repo.list()
    assert [s.slug for s in listed] == sorted(s.slug for s in listed)
    ours = [s for s in listed if s.slug.startswith(stem)]
    assert ours == [
        ProcedureSummary(slug=stem + "-a", title="First"),
        ProcedureSummary(slug=stem + "-b", title="Second"),
        ProcedureSummary(slug=stem + "-c", title="Third"),
    ]


# --- reads: one statement, never mixed ---------------------------------------------


def test_get_reads_in_one_statement(
    repo: PostgresProcedureRepository, app_engine: Engine, slugs: Slugs
) -> None:
    """``get`` reads the procedure and its steps in one join statement."""
    procedure = _procedure(slugs.new(), texts=("One.", "Two.", "Three."))
    repo.save(procedure, ACTOR)
    statements: list[str] = []

    def record(_conn: Any, _cursor: Any, statement: str, *_args: Any) -> None:
        statements.append(statement)

    event.listen(app_engine, "before_cursor_execute", record)
    try:
        assert repo.get(procedure.slug) == _at(procedure, 1)
    finally:
        event.remove(app_engine, "before_cursor_execute", record)
    selects = [s for s in statements if s.lstrip().upper().startswith("SELECT")]
    assert len(selects) == 1
    assert "JOIN" in selects[0].upper()


def test_reader_never_sees_mixed_state(repo: PostgresProcedureRepository, slugs: Slugs) -> None:
    """A reader during imports sees the title and steps of one revision only."""
    slug = slugs.new()
    versions = [
        _procedure(slug, title="Version A", texts=("A one.", "A two.")),
        _procedure(slug, title="Version B", texts=("B one.", "B two.", "B three.")),
    ]
    repo.save(versions[0], ACTOR)
    done = threading.Event()
    failures: list[BaseException] = []

    def write() -> None:
        try:
            for index in range(20):
                repo.save(versions[(index + 1) % 2], ACTOR)
        except BaseException as error:
            failures.append(error)
        finally:
            done.set()

    writer = threading.Thread(target=write)
    writer.start()
    reads = 0
    while not done.is_set() or reads == 0:
        current = repo.get(slug)
        assert current is not None
        assert current.model_copy(update={"revision": None}) in versions
        reads += 1
    writer.join(timeout=30)
    assert failures == []


# --- read speed --------------------------------------------------------------------


def test_reads_are_fast(
    repo: PostgresProcedureRepository, app_engine: Engine, slugs: Slugs
) -> None:
    """Scenario: read speed."""
    made = [_procedure(slugs.new(), texts=("One.", "Two.", "Three.")) for _ in range(3)]
    for procedure in made:
        repo.save(procedure, ACTOR)
    with app_engine.connect() as conn:  # open the pool connection outside the bound
        conn.execute(text("SELECT 1"))
    for procedure in made:
        start = time.perf_counter()
        assert repo.get(procedure.slug) is not None
        assert time.perf_counter() - start < READ_BOUND_SECONDS
    start = time.perf_counter()
    repo.list()
    assert time.perf_counter() - start < READ_BOUND_SECONDS
