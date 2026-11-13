"""The integration fixtures connect as ``lawbyai_app``; the owner only migrates and sets up.

Marked ``integration``. Skipped if PostgreSQL is unreachable.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from factories.scratch_db import ScratchDb, scratch_database
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
ROLE_SQL = "SELECT current_user, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"


def _role(url: str) -> tuple[str, bool, bool]:
    engine = create_engine(url, future=True)
    try:
        with engine.connect() as conn:
            name, superuser, bypass = conn.execute(text(ROLE_SQL)).one()
    finally:
        engine.dispose()
    return str(name), bool(superuser), bool(bypass)


def test_app_connection_is_lawbyai_app(postgres_url: str) -> None:
    assert _role(postgres_url) == ("lawbyai_app", False, False)


@pytest.fixture
def scratch(postgres_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[ScratchDb]:
    """Scratch database at head, migrated with the owner URL."""
    with scratch_database("migroles") as db:
        monkeypatch.setenv("POSTGRES_URL", db.app_url)
        monkeypatch.setenv("POSTGRES_OWNER_URL", db.owner_url)
        cfg = Config(str(REPO_ROOT / "alembic.ini"))
        cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
        command.upgrade(cfg, "head")
        yield db


def test_scratch_migrates_as_owner_and_asserts_as_app(scratch: ScratchDb) -> None:
    engine = create_engine(scratch.app_url, future=True)
    try:
        with engine.connect() as conn:
            owners = set(
                conn.execute(
                    text("SELECT DISTINCT tableowner FROM pg_tables WHERE schemaname = 'public'")
                ).scalars()
            )
    finally:
        engine.dispose()

    assert owners == {"lawbyai_owner"}
    assert _role(scratch.app_url) == ("lawbyai_app", False, False)
    assert _role(scratch.owner_url) == ("lawbyai_owner", False, False)
