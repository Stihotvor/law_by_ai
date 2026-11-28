"""scripts/seed_db.py against a real database (procedure-kb T5).

The seed runs as ``lawbyai_app`` (``POSTGRES_URL``) on an empty scratch database
that the owner migrated to head. Skipped if PostgreSQL is unreachable.
"""

from __future__ import annotations

import importlib.util
import re
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from factories.scratch_db import ScratchDb, scratch_database
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "seed_db.py"
DATA_DIR = REPO_ROOT / "data" / "procedures"
SLUGS = ["pesel", "residence-card", "tax-id"]
PROCEDURES_SQL = "SELECT slug, revision FROM procedure ORDER BY slug"
REVISIONS_SQL = (
    "SELECT p.slug, r.revision, r.actor FROM procedure_revision r "
    "JOIN procedure p ON p.id = r.procedure_id ORDER BY p.slug, r.revision"
)


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("seed_db", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _alembic_config() -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    return cfg


def _rows(url: str, sql: str) -> list[tuple[Any, ...]]:
    engine = create_engine(url, future=True)
    try:
        with engine.connect() as conn:
            return [tuple(row) for row in conn.execute(text(sql)).all()]
    finally:
        engine.dispose()


@pytest.fixture
def migrated_db(postgres_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[ScratchDb]:
    """An empty scratch database at head; ``POSTGRES_URL`` points at it as ``lawbyai_app``."""
    with scratch_database("t5seed") as db:
        monkeypatch.setenv("POSTGRES_URL", db.app_url)
        monkeypatch.setenv("POSTGRES_OWNER_URL", db.owner_url)
        command.upgrade(_alembic_config(), "head")
        yield db


def test_seed_twice(migrated_db: ScratchDb, capsys: pytest.CaptureFixture[str]) -> None:
    """Scenario: seed twice."""
    module = _load()
    assert module.main([str(DATA_DIR)]) == 0
    first_out = capsys.readouterr().out.splitlines()
    assert first_out == [f"{slug} revision=1 changed=True" for slug in SLUGS]
    first = _rows(migrated_db.app_url, REVISIONS_SQL)
    assert first == [(slug, 1, "system:seed") for slug in SLUGS]

    assert module.main([str(DATA_DIR)]) == 0
    second_out = capsys.readouterr().out.splitlines()
    assert second_out == [f"{slug} revision=1 changed=False" for slug in SLUGS]
    assert _rows(migrated_db.app_url, REVISIONS_SQL) == first
    assert _rows(migrated_db.app_url, PROCEDURES_SQL) == [(slug, 1) for slug in SLUGS]


def test_qa_079_seed_edit_adds_a_revision(migrated_db: ScratchDb, tmp_path: Path) -> None:
    module = _load()
    assert module.main([str(DATA_DIR)]) == 0
    for path in DATA_DIR.glob("*.yaml"):
        (tmp_path / path.name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    target = tmp_path / "pesel.yaml"
    original = target.read_text(encoding="utf-8")
    edited = re.sub(r"last_checked: \S+", "last_checked: 2000-01-01", original, count=1)
    assert edited != original
    target.write_text(edited, encoding="utf-8")
    assert module.main([str(tmp_path)]) == 0
    expected = [(slug, 2 if slug == "pesel" else 1) for slug in SLUGS]
    assert _rows(migrated_db.app_url, PROCEDURES_SQL) == expected


def test_bad_file_writes_nothing(migrated_db: ScratchDb, tmp_path: Path) -> None:
    """A bad file next to a good one: the seed exits non-zero and the tables stay empty."""
    good = (DATA_DIR / "pesel.yaml").read_text(encoding="utf-8")
    (tmp_path / "pesel.yaml").write_text(good, encoding="utf-8")
    bad = good.replace("slug: pesel", "slug: bad-one").replace(
        "source_url: https://", "source_url: http://", 1
    )
    assert bad != good
    (tmp_path / "bad-one.yaml").write_text(bad, encoding="utf-8")
    assert _load().main([str(tmp_path)]) != 0
    assert _rows(migrated_db.app_url, PROCEDURES_SQL) == []
    assert _rows(migrated_db.app_url, REVISIONS_SQL) == []
