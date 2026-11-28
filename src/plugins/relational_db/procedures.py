"""PostgreSQL adapter of the ``ProcedureRepository`` port.

A direct integration beside ``PostgreSQLStore`` (ADR-0014), not a method of it:
procedures are a separate aggregate. Each call opens its own session. Reads
return frozen pydantic objects, so nothing lazy-loads after the session closes.

``save`` runs in one READ COMMITTED transaction with ``lock_timeout`` set to
``LOCK_TIMEOUT``, in this order:

1. ``INSERT ... ON CONFLICT (slug) DO UPDATE SET slug = EXCLUDED.slug RETURNING
   id, revision``. This locks the row, also for a new slug.
2. Compare the content (``model_dump(mode="json")`` without ``revision``) with
   the latest revision row (jsonb equality). If equal, roll back: no write, and
   ``updated_at`` stays.
3. Delete the steps and insert the new steps.
4. ``UPDATE procedure SET revision = revision + 1`` (``1`` on the first import),
   then insert the revision row with the actor.

The repository never deletes a procedure: the revision foreign key is RESTRICT
and ``lawbyai_app`` has no DELETE on ``procedure``. Database errors (also a lock
timeout, SQLSTATE 55P03) and stored rows that fail validation map to
``ProcedureStoreError`` with the cause chained and no content in the message.
"""

from __future__ import annotations

import builtins
import enum
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any

from pydantic import ValidationError
from sqlalchemy import Engine, RowMapping, cast, delete, func, insert, select, text, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from core.procedures import ImportResult, Procedure, ProcedureStoreError, ProcedureSummary
from data.models import Procedure as ProcedureRow
from data.models import ProcedureRevision, ProcedureStep

__all__ = ["PostgresProcedureRepository"]

ISOLATION = {"isolation_level": "READ COMMITTED"}
LOCK_TIMEOUT = "5s"
_SET_LOCK_TIMEOUT = text(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'")
_STEP_FIELDS = ("key", "text", "source_url", "last_checked", "verify_with_office")


@contextmanager
def _store_errors(operation: str) -> Iterator[None]:
    """Map database and row validation errors to ``ProcedureStoreError``.

    The message names the operation only. A lock timeout (SQLSTATE 55P03) is an
    ``OperationalError``, so it maps here too.
    """
    try:
        yield
    except (SQLAlchemyError, ValidationError) as exc:
        raise ProcedureStoreError(f"procedure store failed: {operation}") from exc


def _lock_row(session: Session, procedure: Procedure) -> tuple[int, int]:
    """Step 1: upsert the procedure row by slug and lock it; return ``id`` and ``revision``.

    A new row is inserted at revision 1 already, so the first import keeps 1.
    """
    stmt = pg_insert(ProcedureRow).values(
        slug=procedure.slug,
        title=procedure.title,
        schema_version=procedure.schema_version,
        revision=1,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[ProcedureRow.slug], set_={"slug": stmt.excluded.slug}
    ).returning(ProcedureRow.id, ProcedureRow.revision)
    row = session.execute(stmt).one()
    return row.id, row.revision


class _Latest(enum.Enum):
    """How *content* compares with the latest revision row."""

    MISSING = "missing"
    EQUAL = "equal"
    DIFFERENT = "different"


def _latest_state(session: Session, procedure_id: int, content: dict[str, Any]) -> _Latest:
    """Step 2: jsonb-compare *content* with the latest revision row, if there is one."""
    same = ProcedureRevision.content == cast(content, JSONB)
    stmt = (
        select(same)
        .where(ProcedureRevision.procedure_id == procedure_id)
        .order_by(ProcedureRevision.revision.desc())
        .limit(1)
    )
    same_content = session.execute(stmt).scalar_one_or_none()
    if same_content is None:
        return _Latest.MISSING
    return _Latest.EQUAL if same_content else _Latest.DIFFERENT


def _replace_steps(session: Session, procedure_id: int, procedure: Procedure) -> None:
    """Step 3: delete the old steps and insert the new ones by position."""
    session.execute(delete(ProcedureStep).where(ProcedureStep.procedure_id == procedure_id))
    rows = [
        {"procedure_id": procedure_id, "position": position, **step.model_dump()}
        for position, step in enumerate(procedure.steps)
    ]
    session.execute(insert(ProcedureStep), rows)


def _bump_revision(session: Session, procedure_id: int, procedure: Procedure, first: bool) -> int:
    """Step 4a: set title, schema version, ``updated_at`` and the next revision.

    On the *first* import the row from step 1 is already at revision 1, so the
    revision stays 1 instead of being bumped.
    """
    stmt = (
        update(ProcedureRow)
        .where(ProcedureRow.id == procedure_id)
        .values(
            title=procedure.title,
            schema_version=procedure.schema_version,
            revision=1 if first else ProcedureRow.revision + 1,
            updated_at=func.now(),
        )
        .returning(ProcedureRow.revision)
    )
    return session.execute(stmt).scalar_one()


def _write(session: Session, procedure: Procedure, actor: str) -> ImportResult:
    """Run the import order; leave the commit or rollback to the caller."""
    content = procedure.model_dump(mode="json", exclude={"revision"})
    procedure_id, current = _lock_row(session, procedure)
    latest = _latest_state(session, procedure_id, content)
    if latest is _Latest.EQUAL:
        return ImportResult(slug=procedure.slug, revision=current, changed=False)
    _replace_steps(session, procedure_id, procedure)
    revision = _bump_revision(session, procedure_id, procedure, first=latest is _Latest.MISSING)
    session.execute(
        insert(ProcedureRevision).values(
            procedure_id=procedure_id, revision=revision, content=content, actor=actor
        )
    )
    return ImportResult(slug=procedure.slug, revision=revision, changed=True)


def _to_procedure(rows: Sequence[RowMapping]) -> Procedure:
    """Build the frozen procedure from the join rows (one row per step, by position)."""
    head = rows[0]
    steps = [{field: row[field] for field in _STEP_FIELDS} for row in rows]
    return Procedure.model_validate(
        {
            "schema_version": head["schema_version"],
            "slug": head["slug"],
            "title": head["title"],
            "steps": steps,
            "revision": head["revision"],
        }
    )


class PostgresProcedureRepository:
    """``ProcedureRepository`` on the ``procedure``, ``procedure_step`` and revision tables."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def save(self, procedure: Procedure, actor: str) -> ImportResult:
        """Store *procedure* as the next revision by *actor*, or write nothing if identical.

        Raises ``ProcedureStoreError`` on a database failure; then nothing is written.
        """
        with _store_errors("save"), Session(self._engine) as session:
            session.connection(execution_options=ISOLATION)
            session.execute(_SET_LOCK_TIMEOUT)
            result = _write(session, procedure, actor)
            if result.changed:
                session.commit()
            else:
                session.rollback()
            return result

    def get(self, slug: str) -> Procedure | None:
        """Return the current procedure with its ``revision``, or ``None`` if not found.

        One join statement, so a reader never mixes an old title with new steps.
        Raises ``ProcedureStoreError`` on a database failure or a stored row that
        fails validation (cause chained, no content in the message).
        """
        stmt = (
            select(
                ProcedureRow.slug,
                ProcedureRow.title,
                ProcedureRow.schema_version,
                ProcedureRow.revision,
                *(getattr(ProcedureStep, field) for field in _STEP_FIELDS),
            )
            .join(ProcedureStep, ProcedureStep.procedure_id == ProcedureRow.id)
            .where(ProcedureRow.slug == slug)
            .order_by(ProcedureStep.position)
        )
        with _store_errors("get"), Session(self._engine) as session:
            rows = session.execute(stmt).mappings().all()
            return _to_procedure(rows) if rows else None

    def list(self) -> builtins.list[ProcedureSummary]:
        """Return a summary of every stored procedure, sorted by slug."""
        stmt = select(ProcedureRow.slug, ProcedureRow.title).order_by(ProcedureRow.slug)
        with _store_errors("list"), Session(self._engine) as session:
            rows = session.execute(stmt).all()
        return [ProcedureSummary(slug=row.slug, title=row.title) for row in rows]
