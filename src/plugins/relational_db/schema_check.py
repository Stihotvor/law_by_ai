"""Check that the database schema is at the Alembic head. It never migrates."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine

__all__ = ["SchemaNotAtHeadError", "check_schema_head"]


class SchemaNotAtHeadError(RuntimeError):
    """The database revision differs from the Alembic head; run the migrations."""

    def __init__(self, current: str | None, head: str | None) -> None:
        self.current, self.head = current, head
        super().__init__(
            f"database schema is at revision {current or '<none>'}, "
            f"expected head {head or '<none>'}: run 'alembic upgrade head' as lawbyai_owner"
        )


def _alembic_head() -> str | None:
    """Return the head revision of the repo's ``migrations/`` scripts."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[3] / "migrations"))
    return ScriptDirectory.from_config(cfg).get_current_head()


def check_schema_head(engine: Engine) -> None:
    """Raise :class:`SchemaNotAtHeadError` unless the DB is at head. Never migrates."""
    from alembic.runtime.migration import MigrationContext

    head = _alembic_head()
    with engine.connect() as conn:
        current = MigrationContext.configure(conn).get_current_revision()
    if current != head:
        raise SchemaNotAtHeadError(current, head)
